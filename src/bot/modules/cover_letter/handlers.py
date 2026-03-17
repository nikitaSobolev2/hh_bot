"""Handlers for cover letter module (main menu flow)."""

from __future__ import annotations

import contextlib

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.modules.cover_letter.callbacks import CoverLetterCallback
from src.bot.modules.cover_letter.keyboards import (
    cover_letter_detail_keyboard,
    cover_letter_hub_keyboard,
    cover_letter_list_keyboard,
    enter_url_keyboard,
)
from src.bot.modules.cover_letter.services import fetch_and_upsert_vacancy, parse_hh_vacancy_id
from src.bot.modules.cover_letter.states import CoverLetterForm
from src.bot.utils.limits import get_max_message_length
from src.core.i18n import I18nContext
from src.models.user import User
from src.repositories.autoparse import AutoparsedVacancyRepository
from src.repositories.cover_letter_vacancy import CoverLetterVacancyRepository
from src.repositories.task import CeleryTaskRepository

router = Router(name="cover_letter")

_PAGE_SIZE = 10


def _parse_idempotency_key(key: str) -> tuple[str, int] | None:
    """Parse idempotency_key to (source, vacancy_id). Returns None if invalid."""
    parts = key.split(":")
    if len(parts) == 4:
        try:
            return parts[2], int(parts[3])
        except ValueError:
            return None
    if len(parts) == 3:
        try:
            return "autoparse", int(parts[2])
        except ValueError:
            return None
    return None


async def show_cover_letter_hub(
    callback: CallbackQuery,
    i18n: I18nContext,
) -> None:
    """Show cover letter hub: generate new, my letters, back."""
    text = i18n.get("cl-hub-title")
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=cover_letter_hub_keyboard(i18n),
        )


async def show_cover_letter_list(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
    page: int = 0,
) -> None:
    """Show list of user's generated cover letters."""
    task_repo = CeleryTaskRepository(session)
    tasks = await task_repo.get_cover_letter_tasks_by_user(
        user.id, offset=page * _PAGE_SIZE, limit=_PAGE_SIZE
    )
    total = await task_repo.count_cover_letter_tasks_by_user(user.id)

    items: list[tuple[int, str, str, int, str]] = []
    autoparse_repo = AutoparsedVacancyRepository(session)
    standalone_repo = CoverLetterVacancyRepository(session)

    for task in tasks:
        parsed = _parse_idempotency_key(task.idempotency_key)
        if not parsed:
            continue
        source, vacancy_id = parsed
        vacancy = None
        if source == "standalone":
            vacancy = await standalone_repo.get_by_id(vacancy_id)
        else:
            vacancy = await autoparse_repo.get_by_id(vacancy_id)

        title = vacancy.title if vacancy else i18n.get("cl-unknown-vacancy")
        date_str = task.updated_at.strftime("%d.%m %H:%M") if task.updated_at else ""
        items.append((task.id, title, date_str, vacancy_id, source))

    text = i18n.get("cl-list-empty") if not items and page == 0 else i18n.get("cl-list-title")
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=cover_letter_list_keyboard(items, page, total, i18n),
        )


@router.callback_query(CoverLetterCallback.filter(F.action == "generate_new"))
async def handle_generate_new(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await callback.answer()
    await state.set_state(CoverLetterForm.waiting_url)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("cl-enter-url"),
            reply_markup=enter_url_keyboard(i18n),
        )


@router.callback_query(CoverLetterCallback.filter(F.action == "cancel_url"))
async def handle_cancel_url(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await callback.answer()
    await state.clear()
    await show_cover_letter_hub(callback, i18n)


@router.message(CoverLetterForm.waiting_url, F.text)
async def handle_url_input(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    url = (message.text or "").strip()
    if not url.startswith("http"):
        await message.answer(
            i18n.get("cl-invalid-url"),
            reply_markup=enter_url_keyboard(i18n),
        )
        return

    if not parse_hh_vacancy_id(url):
        await message.answer(
            i18n.get("cl-invalid-url"),
            reply_markup=enter_url_keyboard(i18n),
        )
        return

    wait_msg = await message.answer(i18n.get("cl-fetching"))

    vacancy = await fetch_and_upsert_vacancy(session, user.id, url)
    if not vacancy:
        await wait_msg.edit_text(
            i18n.get("cl-fetch-failed"),
            reply_markup=enter_url_keyboard(i18n),
        )
        return

    await session.commit()
    await state.clear()

    from src.bot.modules.autoparse import services as ap_service
    from src.core.celery_async import run_celery_task
    from src.worker.tasks.cover_letter import generate_cover_letter_task

    current = await ap_service.get_user_autoparse_settings(session, user.id)
    cover_letter_style = current.get("cover_letter_style", "professional")

    with contextlib.suppress(TelegramBadRequest):
        await wait_msg.edit_text(i18n.get("cl-generating"))

    await run_celery_task(
        generate_cover_letter_task,
        user.id,
        vacancy.id,
        message.chat.id,
        wait_msg.message_id,
        user.language_code or "ru",
        cover_letter_style,
        0,
        "standalone",
    )


@router.callback_query(CoverLetterCallback.filter(F.action == "list"))
async def handle_list(
    callback: CallbackQuery,
    callback_data: CoverLetterCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await callback.answer()
    await show_cover_letter_list(callback, user, session, i18n, callback_data.page)


@router.callback_query(CoverLetterCallback.filter(F.action == "detail"))
async def handle_detail(
    callback: CallbackQuery,
    callback_data: CoverLetterCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await callback.answer()

    task_repo = CeleryTaskRepository(session)
    task = await task_repo.get_by_id(callback_data.task_id)
    if not task or task.user_id != user.id or task.task_type != "cover_letter":
        await callback.answer(i18n.get("cl-not-found"), show_alert=True)
        return

    source = callback_data.source or "autoparse"
    vacancy_id = callback_data.vacancy_id
    vacancy = None
    if source == "standalone":
        vacancy = await CoverLetterVacancyRepository(session).get_by_id(vacancy_id)
    else:
        vacancy = await AutoparsedVacancyRepository(session).get_by_id(vacancy_id)

    if not vacancy:
        await callback.answer(i18n.get("cl-not-found"), show_alert=True)
        return

    generated_text = (task.result_data or {}).get("generated_text", "")
    if not generated_text:
        generated_text = i18n.get("feed-cover-letter-generated")

    max_len = get_max_message_length(user, "default")
    if len(generated_text) > max_len:
        generated_text = generated_text[: max_len - 10] + "\n..."

    vacancy_url = vacancy.url if hasattr(vacancy, "url") else f"https://hh.ru/vacancy/{vacancy.hh_vacancy_id}"

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            generated_text,
            reply_markup=cover_letter_detail_keyboard(
                task.id,
                vacancy_id,
                source,
                vacancy_url,
                i18n,
            ),
        )


@router.callback_query(CoverLetterCallback.filter(F.action == "regenerate"))
async def handle_regenerate(
    callback: CallbackQuery,
    callback_data: CoverLetterCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await callback.answer()

    source = callback_data.source or "standalone"
    vacancy_id = callback_data.vacancy_id

    idempotency_key = f"cover_letter:{user.id}:{source}:{vacancy_id}"
    await CeleryTaskRepository(session).delete_by_idempotency_key(idempotency_key)
    await session.commit()

    from src.bot.modules.autoparse import services as ap_service
    from src.core.celery_async import run_celery_task
    from src.worker.tasks.cover_letter import generate_cover_letter_task

    current = await ap_service.get_user_autoparse_settings(session, user.id)
    cover_letter_style = current.get("cover_letter_style", "professional")

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(i18n.get("cl-generating"))

    await run_celery_task(
        generate_cover_letter_task,
        user.id,
        vacancy_id,
        callback.message.chat.id,
        callback.message.message_id,
        user.language_code or "ru",
        cover_letter_style,
        0,
        source,
    )
