"""Handlers for the Vacancy Summary (about-me) module."""

from __future__ import annotations

import contextlib

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.modules.vacancy_summary.callbacks import VacancySummaryCallback
from src.bot.modules.vacancy_summary.keyboards import (
    skip_keyboard,
    vacancy_summary_detail_keyboard,
    vacancy_summary_list_keyboard,
)
from src.bot.modules.vacancy_summary.states import VacancySummaryForm
from src.core.i18n import I18nContext
from src.models.user import User
from src.repositories.vacancy_summary import VacancySummaryRepository

router = Router(name="vacancy_summary")

_FORM_STEPS = ["excluded_industries", "location", "remote_preference", "additional_notes"]


async def show_vacancy_summary_list(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
    page: int = 0,
) -> None:
    repo = VacancySummaryRepository(session)
    summaries, total = await repo.get_by_user_paginated(user.id, page)

    text = (
        f"<b>{i18n.get('vs-list-empty')}</b>"
        if not summaries and page == 0
        else f"<b>{i18n.get('vs-list-title')}</b>"
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=vacancy_summary_list_keyboard(summaries, page, total, i18n),
        )


@router.callback_query(VacancySummaryCallback.filter(F.action == "list"))
async def handle_list(
    callback: CallbackQuery,
    callback_data: VacancySummaryCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await show_vacancy_summary_list(callback, user, session, i18n, callback_data.page)
    await callback.answer()


@router.callback_query(VacancySummaryCallback.filter(F.action == "generate_new"))
async def handle_generate_new(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.clear()
    await state.update_data(
        vs_step=0,
        vs_excluded_industries=None,
        vs_location=None,
        vs_remote_preference=None,
        vs_additional_notes=None,
    )
    await state.set_state(VacancySummaryForm.excluded_industries)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("vs-enter-excluded-industries"),
            reply_markup=skip_keyboard(i18n),
        )
    await callback.answer()


@router.message(VacancySummaryForm.excluded_industries)
async def fsm_excluded_industries(message: Message, state: FSMContext, i18n: I18nContext) -> None:
    await state.update_data(vs_excluded_industries=(message.text or "").strip() or None)
    await state.set_state(VacancySummaryForm.location)
    await message.answer(i18n.get("vs-enter-location"), reply_markup=skip_keyboard(i18n))


@router.message(VacancySummaryForm.location)
async def fsm_location(message: Message, state: FSMContext, i18n: I18nContext) -> None:
    await state.update_data(vs_location=(message.text or "").strip() or None)
    await state.set_state(VacancySummaryForm.remote_preference)
    await message.answer(i18n.get("vs-enter-remote"), reply_markup=skip_keyboard(i18n))


@router.message(VacancySummaryForm.remote_preference)
async def fsm_remote_preference(message: Message, state: FSMContext, i18n: I18nContext) -> None:
    await state.update_data(vs_remote_preference=(message.text or "").strip() or None)
    await state.set_state(VacancySummaryForm.additional_notes)
    await message.answer(i18n.get("vs-enter-additional"), reply_markup=skip_keyboard(i18n))


@router.message(VacancySummaryForm.additional_notes)
async def fsm_additional_notes(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await state.update_data(vs_additional_notes=(message.text or "").strip() or None)
    await _dispatch_generation(message, user, state, session, i18n)


@router.callback_query(VacancySummaryCallback.filter(F.action == "skip_step"))
async def handle_skip_step(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    current_state = await state.get_state()
    if current_state == VacancySummaryForm.excluded_industries:
        await state.set_state(VacancySummaryForm.location)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("vs-enter-location"), reply_markup=skip_keyboard(i18n)
            )
    elif current_state == VacancySummaryForm.location:
        await state.set_state(VacancySummaryForm.remote_preference)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("vs-enter-remote"), reply_markup=skip_keyboard(i18n)
            )
    elif current_state == VacancySummaryForm.remote_preference:
        await state.set_state(VacancySummaryForm.additional_notes)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("vs-enter-additional"), reply_markup=skip_keyboard(i18n)
            )
    elif current_state == VacancySummaryForm.additional_notes:
        await _dispatch_generation(callback.message, user, state, session, i18n, edit=True)
    await callback.answer()


@router.callback_query(VacancySummaryCallback.filter(F.action == "cancel"))
async def handle_cancel(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await state.clear()
    await show_vacancy_summary_list(callback, user, session, i18n)
    await callback.answer()


def _enqueue_summary(
    summary_id: int,
    user_id: int,
    excluded_industries: str | None,
    location: str | None,
    remote_preference: str | None,
    additional_notes: str | None,
    chat_id: int,
    message_id: int,
    locale: str,
) -> None:
    from src.worker.tasks.vacancy_summary import generate_vacancy_summary_task

    generate_vacancy_summary_task.delay(
        summary_id,
        user_id,
        excluded_industries,
        location,
        remote_preference,
        additional_notes,
        chat_id,
        message_id,
        locale,
    )


async def _dispatch_generation(
    message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
    *,
    edit: bool = False,
) -> None:
    data = await state.get_data()
    await state.clear()

    excluded_industries = data.get("vs_excluded_industries")
    location = data.get("vs_location")
    remote_preference = data.get("vs_remote_preference")
    additional_notes = data.get("vs_additional_notes")

    repo = VacancySummaryRepository(session)
    summary = await repo.create(
        user.id,
        excluded_industries=excluded_industries,
        location=location,
        remote_preference=remote_preference,
        additional_notes=additional_notes,
    )
    await session.commit()

    if edit:
        wait_msg = await message.edit_text(i18n.get("vs-generating"))
    else:
        wait_msg = await message.answer(i18n.get("vs-generating"))

    _enqueue_summary(
        summary.id,
        user.id,
        excluded_industries,
        location,
        remote_preference,
        additional_notes,
        message.chat.id,
        wait_msg.message_id if wait_msg else message.message_id,
        user.language_code or "ru",
    )


@router.callback_query(VacancySummaryCallback.filter(F.action == "detail"))
async def handle_detail(
    callback: CallbackQuery,
    callback_data: VacancySummaryCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    repo = VacancySummaryRepository(session)
    summary = await repo.get_by_id(callback_data.summary_id)
    if not summary or summary.is_deleted or summary.user_id != user.id:
        await callback.answer(i18n.get("vs-not-found"), show_alert=True)
        return

    text = summary.generated_text or i18n.get("vs-generating")
    if len(text) > 4000:
        text = text[:3900] + "\n..."

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=vacancy_summary_detail_keyboard(summary.id, i18n),
        )
    await callback.answer()


@router.callback_query(VacancySummaryCallback.filter(F.action == "regenerate"))
async def handle_regenerate(
    callback: CallbackQuery,
    callback_data: VacancySummaryCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    repo = VacancySummaryRepository(session)
    old_summary = await repo.get_by_id(callback_data.summary_id)

    if not old_summary or old_summary.user_id != user.id:
        await callback.answer(i18n.get("vs-not-found"), show_alert=True)
        return

    await callback.answer()

    has_stored_params = any(
        getattr(old_summary, field) is not None
        for field in ("excluded_industries", "location", "remote_preference", "additional_notes")
    )

    await repo.soft_delete(old_summary)
    await session.commit()

    if not has_stored_params:
        # Legacy row: no params were stored — restart the input wizard
        await state.clear()
        await state.update_data(
            vs_excluded_industries=None,
            vs_location=None,
            vs_remote_preference=None,
            vs_additional_notes=None,
        )
        await state.set_state(VacancySummaryForm.excluded_industries)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("vs-enter-excluded-industries"),
                reply_markup=skip_keyboard(i18n),
            )
        return

    # Clone params from the old summary and dispatch immediately
    new_summary = await repo.create(
        user.id,
        excluded_industries=old_summary.excluded_industries,
        location=old_summary.location,
        remote_preference=old_summary.remote_preference,
        additional_notes=old_summary.additional_notes,
    )
    await session.commit()

    wait_msg = None
    with contextlib.suppress(TelegramBadRequest):
        wait_msg = await callback.message.edit_text(i18n.get("vs-generating"))

    _enqueue_summary(
        new_summary.id,
        user.id,
        new_summary.excluded_industries,
        new_summary.location,
        new_summary.remote_preference,
        new_summary.additional_notes,
        callback.message.chat.id,
        wait_msg.message_id if wait_msg else callback.message.message_id,
        user.language_code or "ru",
    )


@router.callback_query(VacancySummaryCallback.filter(F.action == "delete"))
async def handle_delete(
    callback: CallbackQuery,
    callback_data: VacancySummaryCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await callback.answer(i18n.get("vs-deleted"))

    repo = VacancySummaryRepository(session)
    summary = await repo.get_by_id(callback_data.summary_id)
    if summary and summary.user_id == user.id:
        await repo.soft_delete(summary)
        await session.commit()
    await show_vacancy_summary_list(callback, user, session, i18n)
