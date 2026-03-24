"""Handlers for the interactive vacancy feed."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.modules.autoparse import feed_services
from src.core.logging import get_logger
from src.bot.modules.autoparse.callbacks import FeedCallback
from src.bot.modules.autoparse.states import FeedRespondForm
from src.core.i18n import I18nContext
from src.models.user import User
from src.models.vacancy_feed import VacancyFeedSession
from src.repositories.autoparse import AutoparsedVacancyRepository
from src.repositories.hh_application_attempt import HhApplicationAttemptRepository
from src.repositories.hh_linked_account import HhLinkedAccountRepository
from src.repositories.vacancy_feed import VacancyFeedSessionRepository

router = Router(name="feed")

logger = get_logger(__name__)

# Playwright resume list can be slow; show loading UI and cap wait so the user is not stuck silent.
_LIST_RESUMES_TIMEOUT_S = 120.0


def _resume_cache_to_lists(resume_list_cache: list | None) -> tuple[list[str], list[str]] | None:
    if not resume_list_cache or not isinstance(resume_list_cache, list):
        return None
    ids: list[str] = []
    titles: list[str] = []
    for it in resume_list_cache[:12]:
        if not isinstance(it, dict):
            return None
        rid = it.get("id")
        if rid is None or str(rid).strip() == "":
            return None
        title = it.get("title")
        if title is None:
            title = str(rid)
        ids.append(str(rid))
        titles.append(str(title)[:60])
    if not ids:
        return None
    return ids, titles


def feed_respond_resume_keyboard(
    session_id: int,
    vacancy_id: int,
    titles: list[str],
    i18n: I18nContext,
    *,
    show_refresh: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for idx, title in enumerate(titles[:12]):
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{idx + 1}. {title}"[:64],
                    callback_data=FeedCallback(
                        action="respond_pick",
                        session_id=session_id,
                        vacancy_id=vacancy_id,
                        resume_idx=idx,
                    ).pack(),
                )
            ]
        )
    if show_refresh:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("feed-btn-refresh-resumes"),
                    callback_data=FeedCallback(
                        action="respond_refresh_resumes",
                        session_id=session_id,
                        vacancy_id=vacancy_id,
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-cancel"),
                callback_data=FeedCallback(
                    action="respond_cancel",
                    session_id=session_id,
                    vacancy_id=vacancy_id,
                ).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def feed_respond_letter_keyboard(
    session_id: int,
    vacancy_id: int,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("feed-respond-letter-generate"),
                    callback_data=FeedCallback(
                        action="respond_letter_generate",
                        session_id=session_id,
                        vacancy_id=vacancy_id,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("feed-respond-letter-skip"),
                    callback_data=FeedCallback(
                        action="respond_letter_skip",
                        session_id=session_id,
                        vacancy_id=vacancy_id,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=FeedCallback(
                        action="respond_cancel",
                        session_id=session_id,
                        vacancy_id=vacancy_id,
                    ).pack(),
                ),
            ],
        ]
    )


async def _run_list_resumes_ui_feed(
    storage_state: dict,
    user_id: int,
):
    from src.services.hh_ui.config import HhUiApplyConfig
    from src.services.hh_ui.runner import list_resumes_ui

    cfg = HhUiApplyConfig.from_settings()
    return await asyncio.wait_for(
        asyncio.to_thread(
            list_resumes_ui,
            storage_state=storage_state,
            config=cfg,
            log_user_id=user_id,
        ),
        timeout=_LIST_RESUMES_TIMEOUT_S,
    )


async def _send_feed_respond_resume_choice(
    message,
    state: FSMContext,
    feed_session: VacancyFeedSession,
    vacancy,
    resume_ids: list[str],
    titles: list[str],
    i18n: I18nContext,
    *,
    show_refresh: bool,
    respond_mode: str = "letter_then_apply",
) -> None:
    await state.set_state(FeedRespondForm.choosing_resume)
    await state.update_data(
        feed_session_id=feed_session.id,
        vacancy_id=vacancy.id,
        resume_ids=resume_ids,
        respond_mode=respond_mode,
    )
    kb = feed_respond_resume_keyboard(
        feed_session.id,
        vacancy.id,
        titles,
        i18n,
        show_refresh=show_refresh,
    )
    with contextlib.suppress(TelegramBadRequest):
        await message.edit_text(
            i18n.get("feed-respond-pick-resume"),
            reply_markup=kb,
            parse_mode="HTML",
        )


def _feed_show_respond_button(feed_session: VacancyFeedSession) -> bool:
    """Respond requires a linked HH account on this feed session."""
    return feed_session.hh_linked_account_id is not None


def _feed_vacancy_keyboard_options(
    feed_session: VacancyFeedSession,
    vacancy_id: int,
) -> dict:
    """Shared flags for feed_vacancy_keyboard (liked state, AI respond row)."""
    from src.config import settings

    show = _feed_show_respond_button(feed_session)
    return {
        "vacancy_is_liked": vacancy_id in (feed_session.liked_ids or []),
        "show_respond_ai": bool(show and settings.hh_ui_apply_enabled),
    }


def feed_vacancy_keyboard(
    session_id: int,
    vacancy_id: int,
    vacancy_url: str,
    i18n: I18nContext,
    mode: str = "summary",
    *,
    current_index: int = 0,
    show_respond: bool = True,
    vacancy_is_liked: bool = False,
    show_respond_ai: bool = False,
) -> InlineKeyboardMarkup:
    from src.bot.modules.autoparse.callbacks import AutoparseCallback

    next_mode = "description" if mode == "summary" else "summary"
    toggle_key = "feed-btn-show-description" if mode == "summary" else "feed-btn-show-summary"
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=i18n.get("feed-btn-open"),
                url=vacancy_url,
            )
        ],
        [
            InlineKeyboardButton(
                text=i18n.get(toggle_key),
                callback_data=FeedCallback(
                    action="toggle_view",
                    session_id=session_id,
                    vacancy_id=vacancy_id,
                    mode=next_mode,
                ).pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text=i18n.get(
                    "feed-btn-fits-me-liked" if vacancy_is_liked else "feed-btn-fits-me"
                ),
                callback_data=FeedCallback(
                    action="like", session_id=session_id, vacancy_id=vacancy_id
                ).pack(),
            ),
            InlineKeyboardButton(
                text=i18n.get("feed-btn-not-fit"),
                callback_data=FeedCallback(
                    action="dislike", session_id=session_id, vacancy_id=vacancy_id
                ).pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text=i18n.get("feed-btn-create-cover-letter"),
                callback_data=FeedCallback(
                    action="create_cover_letter",
                    session_id=session_id,
                    vacancy_id=vacancy_id,
                ).pack(),
            ),
        ],
    ]
    respond_row: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=i18n.get("feed-btn-respond-hh"),
                callback_data=FeedCallback(
                    action="respond",
                    session_id=session_id,
                    vacancy_id=vacancy_id,
                ).pack(),
            ),
        ],
    ]
    if show_respond_ai:
        respond_row.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("feed-btn-respond-ai-cover"),
                    callback_data=FeedCallback(
                        action="respond_ai_cover",
                        session_id=session_id,
                        vacancy_id=vacancy_id,
                    ).pack(),
                ),
            ]
        )
    tail_rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=i18n.get("feed-btn-show-later"),
                callback_data=FeedCallback(
                    action="show_later", session_id=session_id, vacancy_id=vacancy_id
                ).pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text=i18n.get("feed-btn-stop"),
                callback_data=FeedCallback(action="stop", session_id=session_id).pack(),
            )
        ],
    ]
    if current_index > 0:
        tail_rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=FeedCallback(
                        action="prev_vacancy",
                        session_id=session_id,
                        vacancy_id=vacancy_id,
                    ).pack(),
                )
            ]
        )
    else:
        tail_rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=AutoparseCallback(action="hub").pack(),
                )
            ]
        )
    rows.extend(respond_row if show_respond else [])
    rows.extend(tail_rows)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def feed_start_keyboard(session_id: int, i18n: I18nContext) -> InlineKeyboardMarkup:
    from src.bot.modules.autoparse.callbacks import AutoparseCallback

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("feed-btn-start"),
                    callback_data=FeedCallback(action="start", session_id=session_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("feed-btn-stop"),
                    callback_data=FeedCallback(action="stop", session_id=session_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=AutoparseCallback(action="hub").pack(),
                )
            ],
        ]
    )


@router.callback_query(FeedCallback.filter(F.action == "toggle_view"))
async def handle_feed_toggle_view(
    callback: CallbackQuery,
    callback_data: FeedCallback,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    feed_session = await feed_services.get_feed_session(session, callback_data.session_id)
    if not feed_session or feed_session.is_completed:
        await callback.answer()
        return

    vacancy_repo = AutoparsedVacancyRepository(session)
    vacancy = await vacancy_repo.get_by_id(callback_data.vacancy_id)
    if not vacancy:
        await callback.answer()
        return

    total = len(feed_session.vacancy_ids)
    mode = callback_data.mode
    text = feed_services.build_vacancy_card(
        vacancy, feed_session.current_index, total, i18n.locale, mode
    )
    keyboard = feed_vacancy_keyboard(
        feed_session.id, vacancy.id, vacancy.url, i18n, mode,
        current_index=feed_session.current_index,
        show_respond=_feed_show_respond_button(feed_session),
        **_feed_vacancy_keyboard_options(feed_session, vacancy.id),
    )

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(FeedCallback.filter(F.action == "start"))
async def handle_feed_start(
    callback: CallbackQuery,
    callback_data: FeedCallback,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    feed_session = await feed_services.get_feed_session(session, callback_data.session_id)
    if not feed_session or feed_session.is_completed:
        await callback.answer(i18n.get("feed-session-not-found"), show_alert=True)
        return

    if feed_session.hh_linked_account_id is None:
        hh_repo = HhLinkedAccountRepository(session)
        accs = await hh_repo.list_active_for_user(user.id)
        if len(accs) > 1:
            await callback.answer(i18n.get("feed-pick-hh-first"), show_alert=True)
            return
        if len(accs) == 1:
            feed_repo = VacancyFeedSessionRepository(session)
            await feed_repo.update(feed_session, hh_linked_account_id=accs[0].id)
            await session.commit()

    vacancy_repo = AutoparsedVacancyRepository(session)
    vacancy_id = feed_session.vacancy_ids[feed_session.current_index]
    vacancy = await vacancy_repo.get_by_id(vacancy_id)
    if not vacancy:
        await callback.answer()
        return

    total = len(feed_session.vacancy_ids)
    text = feed_services.build_vacancy_card(vacancy, feed_session.current_index, total, i18n.locale)
    keyboard = feed_vacancy_keyboard(
        feed_session.id, vacancy.id, vacancy.url, i18n,
        current_index=feed_session.current_index,
        show_respond=_feed_show_respond_button(feed_session),
        **_feed_vacancy_keyboard_options(feed_session, vacancy.id),
    )

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(FeedCallback.filter(F.action.in_({"like", "dislike"})))
async def handle_feed_react(
    callback: CallbackQuery,
    callback_data: FeedCallback,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    feed_session = await feed_services.get_feed_session(session, callback_data.session_id)
    if not feed_session or feed_session.is_completed:
        await callback.answer()
        return

    is_like = callback_data.action == "like"
    await feed_services.record_reaction(session, feed_session, callback_data.vacancy_id, is_like)

    total = len(feed_session.vacancy_ids)
    if feed_session.current_index >= total:
        await _show_results(callback, session, feed_session, i18n)
        return

    vacancy_repo = AutoparsedVacancyRepository(session)
    next_vacancy_id = feed_session.vacancy_ids[feed_session.current_index]
    vacancy = await vacancy_repo.get_by_id(next_vacancy_id)
    if not vacancy:
        await callback.answer()
        return

    text = feed_services.build_vacancy_card(vacancy, feed_session.current_index, total, i18n.locale)
    keyboard = feed_vacancy_keyboard(
        feed_session.id, vacancy.id, vacancy.url, i18n,
        current_index=feed_session.current_index,
        show_respond=_feed_show_respond_button(feed_session),
        **_feed_vacancy_keyboard_options(feed_session, vacancy.id),
    )

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


async def _feed_show_next_vacancy_or_results(
    callback: CallbackQuery,
    session: AsyncSession,
    feed_session: VacancyFeedSession,
    i18n: I18nContext,
) -> None:
    total = len(feed_session.vacancy_ids)
    if feed_session.current_index >= total:
        await _show_results(callback, session, feed_session, i18n)
        return

    vacancy_repo = AutoparsedVacancyRepository(session)
    next_vacancy_id = feed_session.vacancy_ids[feed_session.current_index]
    vacancy = await vacancy_repo.get_by_id(next_vacancy_id)
    if not vacancy:
        await callback.answer()
        return

    text = feed_services.build_vacancy_card(
        vacancy, feed_session.current_index, total, i18n.locale
    )
    keyboard = feed_vacancy_keyboard(
        feed_session.id,
        vacancy.id,
        vacancy.url,
        i18n,
        current_index=feed_session.current_index,
        show_respond=_feed_show_respond_button(feed_session),
        **_feed_vacancy_keyboard_options(feed_session, vacancy.id),
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(FeedCallback.filter(F.action == "show_later"))
async def handle_feed_show_later(
    callback: CallbackQuery,
    callback_data: FeedCallback,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    feed_session = await feed_services.get_feed_session(session, callback_data.session_id)
    if not feed_session or feed_session.is_completed:
        await callback.answer()
        return

    await feed_services.move_vacancy_to_end(session, feed_session)

    total = len(feed_session.vacancy_ids)
    if feed_session.current_index >= total:
        await _show_results(callback, session, feed_session, i18n)
        return

    vacancy_repo = AutoparsedVacancyRepository(session)
    next_vacancy_id = feed_session.vacancy_ids[feed_session.current_index]
    vacancy = await vacancy_repo.get_by_id(next_vacancy_id)
    if not vacancy:
        await callback.answer()
        return

    text = feed_services.build_vacancy_card(vacancy, feed_session.current_index, total, i18n.locale)
    keyboard = feed_vacancy_keyboard(
        feed_session.id, vacancy.id, vacancy.url, i18n,
        current_index=feed_session.current_index,
        show_respond=_feed_show_respond_button(feed_session),
        **_feed_vacancy_keyboard_options(feed_session, vacancy.id),
    )

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(FeedCallback.filter(F.action == "create_cover_letter"))
async def handle_feed_create_cover_letter(
    callback: CallbackQuery,
    callback_data: FeedCallback,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    await callback.answer()
    feed_session = await feed_services.get_feed_session(session, callback_data.session_id)
    if not feed_session or feed_session.is_completed:
        return

    vacancy_repo = AutoparsedVacancyRepository(session)
    vacancy = await vacancy_repo.get_by_id(callback_data.vacancy_id)
    if not vacancy:
        return

    from src.bot.modules.autoparse import services as ap_service
    from src.core.celery_async import run_celery_task
    from src.worker.tasks.cover_letter import generate_cover_letter_task

    current = await ap_service.get_user_autoparse_settings(session, user.id)
    cover_letter_style = current.get("cover_letter_style", "professional")

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("feed-cover-letter-generating"),
            parse_mode="HTML",
        )

    await run_celery_task(
        generate_cover_letter_task,
        user.id,
        vacancy.id,
        callback.message.chat.id,
        callback.message.message_id,
        user.language_code or "ru",
        cover_letter_style,
        callback_data.session_id,
    )


@router.callback_query(FeedCallback.filter(F.action == "regenerate_cover_letter"))
async def handle_feed_regenerate_cover_letter(
    callback: CallbackQuery,
    callback_data: FeedCallback,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    feed_session = await feed_services.get_feed_session(session, callback_data.session_id)
    if not feed_session or feed_session.is_completed:
        await callback.answer()
        return

    vacancy_repo = AutoparsedVacancyRepository(session)
    vacancy = await vacancy_repo.get_by_id(callback_data.vacancy_id)
    if not vacancy:
        await callback.answer()
        return

    from src.bot.modules.autoparse import services as ap_service
    from src.core.celery_async import run_celery_task
    from src.repositories.task import CeleryTaskRepository
    from src.worker.tasks.cover_letter import generate_cover_letter_task

    idempotency_key = f"cover_letter:{user.id}:autoparse:{vacancy.id}"
    await CeleryTaskRepository(session).delete_by_idempotency_key(idempotency_key)
    await session.commit()

    current = await ap_service.get_user_autoparse_settings(session, user.id)
    cover_letter_style = current.get("cover_letter_style", "professional")

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("feed-cover-letter-generating"),
            parse_mode="HTML",
        )

    await run_celery_task(
        generate_cover_letter_task,
        user.id,
        vacancy.id,
        callback.message.chat.id,
        callback.message.message_id,
        user.language_code or "ru",
        cover_letter_style,
        callback_data.session_id,
    )
    await callback.answer()


@router.callback_query(FeedCallback.filter(F.action == "back_to_vacancy"))
async def handle_feed_back_to_vacancy(
    callback: CallbackQuery,
    callback_data: FeedCallback,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    feed_session = await feed_services.get_feed_session(session, callback_data.session_id)
    if not feed_session or feed_session.is_completed:
        await callback.answer()
        return

    vacancy_repo = AutoparsedVacancyRepository(session)
    vacancy = await vacancy_repo.get_by_id(callback_data.vacancy_id)
    if not vacancy:
        await callback.answer()
        return

    vacancy_ids = feed_session.vacancy_ids
    current_index = (
        vacancy_ids.index(callback_data.vacancy_id)
        if callback_data.vacancy_id in vacancy_ids
        else 0
    )
    total = len(vacancy_ids)
    text = feed_services.build_vacancy_card(
        vacancy, current_index, total, i18n.locale
    )
    keyboard = feed_vacancy_keyboard(
        feed_session.id, vacancy.id, vacancy.url, i18n,
        current_index=current_index,
        show_respond=_feed_show_respond_button(feed_session),
        **_feed_vacancy_keyboard_options(feed_session, vacancy.id),
    )

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(FeedCallback.filter(F.action == "prev_vacancy"))
async def handle_feed_prev_vacancy(
    callback: CallbackQuery,
    callback_data: FeedCallback,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    feed_session = await feed_services.get_feed_session(session, callback_data.session_id)
    if not feed_session or feed_session.is_completed:
        await callback.answer()
        return

    vacancy_ids = feed_session.vacancy_ids
    try:
        current_idx = vacancy_ids.index(callback_data.vacancy_id)
    except ValueError:
        await callback.answer()
        return
    if current_idx <= 0:
        await callback.answer()
        return

    prev_vacancy_id = vacancy_ids[current_idx - 1]
    from src.repositories.vacancy_feed import VacancyFeedSessionRepository

    feed_repo = VacancyFeedSessionRepository(session)
    await feed_repo.update(feed_session, current_index=current_idx - 1)
    await session.commit()
    feed_session.current_index = current_idx - 1

    vacancy_repo = AutoparsedVacancyRepository(session)
    vacancy = await vacancy_repo.get_by_id(prev_vacancy_id)
    if not vacancy:
        await callback.answer()
        return

    total = len(vacancy_ids)
    text = feed_services.build_vacancy_card(
        vacancy, feed_session.current_index, total, i18n.locale
    )
    keyboard = feed_vacancy_keyboard(
        feed_session.id, vacancy.id, vacancy.url, i18n,
        current_index=feed_session.current_index,
        show_respond=_feed_show_respond_button(feed_session),
        **_feed_vacancy_keyboard_options(feed_session, vacancy.id),
    )

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(FeedCallback.filter(F.action == "pick_hh_account"))
async def handle_feed_pick_hh_account(
    callback: CallbackQuery,
    callback_data: FeedCallback,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    from src.repositories.autoparse import AutoparseCompanyRepository

    feed_session = await feed_services.get_feed_session(session, callback_data.session_id)
    if not feed_session or feed_session.is_completed:
        await callback.answer(i18n.get("feed-session-not-found"), show_alert=True)
        return

    hh_repo = HhLinkedAccountRepository(session)
    acc = await hh_repo.get_by_id(callback_data.hh_account_id)
    if not acc or acc.user_id != user.id or acc.revoked_at:
        await callback.answer(i18n.get("hh-account-not-found"), show_alert=True)
        return

    feed_repo = VacancyFeedSessionRepository(session)
    await feed_repo.update(feed_session, hh_linked_account_id=acc.id)
    await session.commit()

    company_repo = AutoparseCompanyRepository(session)
    company = await company_repo.get_by_id(feed_session.autoparse_company_id)
    if not company:
        await callback.answer()
        return

    vacancy_repo = AutoparsedVacancyRepository(session)
    vacs = await vacancy_repo.get_by_ids_simple(list(feed_session.vacancy_ids))
    by_id = {v.id: v for v in vacs}
    ordered = [by_id[i] for i in feed_session.vacancy_ids if i in by_id]
    compat_scores = [v.compatibility_score for v in ordered if v.compatibility_score is not None]
    avg_compat = sum(compat_scores) / len(compat_scores) if compat_scores else None
    text = feed_services.build_stats_message(
        company.vacancy_title, len(ordered), avg_compat, i18n.locale
    )
    keyboard = feed_start_keyboard(feed_session.id, i18n)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer(i18n.get("hh-account-selected"))


async def _feed_respond_core(
    callback: CallbackQuery,
    callback_data: FeedCallback,
    session: AsyncSession,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
    *,
    respond_mode: str,
    log_event: str,
) -> None:
    from src.config import settings
    from src.services.hh.client import HhApiClient
    from src.services.hh.crypto import HhTokenCipher
    from src.services.hh.token_service import ensure_access_token
    from src.services.hh_ui.outcomes import ApplyOutcome
    from src.services.hh_ui.storage import decrypt_browser_storage

    feed_session = await feed_services.get_feed_session(session, callback_data.session_id)
    if not feed_session or feed_session.is_completed:
        await callback.answer(i18n.get("feed-session-not-found"), show_alert=True)
        return
    if not feed_session.hh_linked_account_id:
        await callback.answer(i18n.get("feed-pick-hh-first"), show_alert=True)
        return

    vacancy_repo = AutoparsedVacancyRepository(session)
    vacancy = await vacancy_repo.get_by_id(callback_data.vacancy_id)
    if not vacancy:
        logger.warning(
            "feed_respond_vacancy_missing",
            user_id=user.id,
            session_id=callback_data.session_id,
            vacancy_id=callback_data.vacancy_id,
        )
        await callback.answer(i18n.get("feed-respond-vacancy-missing"), show_alert=True)
        return

    await feed_services.ensure_liked_for_respond(session, feed_session, vacancy.id)

    logger.info(
        log_event,
        user_id=user.id,
        session_id=callback_data.session_id,
        vacancy_id=vacancy.id,
        ui_apply=settings.hh_ui_apply_enabled,
        respond_mode=respond_mode,
    )

    resume_ids: list[str] = []
    titles: list[str] = []

    if settings.hh_ui_apply_enabled:
        acc_repo = HhLinkedAccountRepository(session)
        acc = await acc_repo.get_by_id(feed_session.hh_linked_account_id)
        if not acc or not acc.browser_storage_enc:
            await callback.answer(i18n.get("feed-respond-no-browser-session"), show_alert=True)
            return
        try:
            cipher = HhTokenCipher(settings.hh_token_encryption_key)
            storage = decrypt_browser_storage(acc.browser_storage_enc, cipher)
        except Exception:
            await callback.answer(i18n.get("hh-token-error"), show_alert=True)
            return
        if not storage:
            await callback.answer(i18n.get("feed-respond-no-browser-session"), show_alert=True)
            return

        cached = _resume_cache_to_lists(acc.resume_list_cache)
        if cached:
            resume_ids, titles = cached
            await callback.answer()
            logger.info(
                "feed_respond_resume_cache_hit",
                user_id=user.id,
                hh_linked_account_id=acc.id,
                resume_count=len(resume_ids),
            )
        else:
            # Telegram callback must be answered within ~10s; list_resumes_ui can take longer.
            await callback.answer()
            with contextlib.suppress(TelegramBadRequest):
                await callback.message.edit_text(
                    i18n.get("feed-respond-loading-resumes"),
                    parse_mode="HTML",
                )
            try:
                lr = await _run_list_resumes_ui_feed(storage, user.id)
            except asyncio.TimeoutError:
                logger.warning(
                    "feed_respond_list_resumes_timeout",
                    user_id=user.id,
                    vacancy_id=vacancy.id,
                    timeout_s=_LIST_RESUMES_TIMEOUT_S,
                )
                with contextlib.suppress(TelegramBadRequest):
                    await callback.message.edit_text(
                        i18n.get("feed-respond-load-timeout"),
                        parse_mode="HTML",
                    )
                return
            except Exception as exc:
                logger.exception(
                    "feed_respond_list_resumes_failed",
                    user_id=user.id,
                    vacancy_id=vacancy.id,
                    error=str(exc),
                )
                with contextlib.suppress(TelegramBadRequest):
                    await callback.message.edit_text(
                        i18n.get("feed-respond-fetch-error"), parse_mode="HTML"
                    )
                return
            if lr.outcome == ApplyOutcome.CAPTCHA:
                with contextlib.suppress(TelegramBadRequest):
                    await callback.message.edit_text(
                        i18n.get("feed-respond-ui-captcha"), parse_mode="HTML"
                    )
                if lr.screenshot_bytes:
                    await callback.message.answer_photo(
                        BufferedInputFile(lr.screenshot_bytes, "hh_captcha.png"),
                    )
                return
            if lr.outcome == ApplyOutcome.SESSION_EXPIRED:
                with contextlib.suppress(TelegramBadRequest):
                    await callback.message.edit_text(
                        i18n.get("feed-respond-ui-session-expired"), parse_mode="HTML"
                    )
                return
            if lr.outcome != ApplyOutcome.SUCCESS or not lr.resumes:
                with contextlib.suppress(TelegramBadRequest):
                    await callback.message.edit_text(
                        i18n.get("feed-respond-fetch-error"), parse_mode="HTML"
                    )
                return
            logger.info(
                "feed_respond_resume_cache_miss",
                user_id=user.id,
                hh_linked_account_id=acc.id,
                resume_count=len(lr.resumes),
            )
            await acc_repo.update_resume_list_cache(
                acc,
                [{"id": r.id, "title": r.title} for r in lr.resumes[:12]],
            )
            await session.commit()
            for r in lr.resumes[:12]:
                resume_ids.append(r.id)
                titles.append(r.title[:60])
    else:
        try:
            _, access = await ensure_access_token(session, feed_session.hh_linked_account_id)
        except Exception:
            await callback.answer(i18n.get("hh-token-error"), show_alert=True)
            return

        await callback.answer()
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("feed-respond-loading-resumes"),
                parse_mode="HTML",
            )
        client = HhApiClient(access)
        try:
            data = await client.get_resumes_mine(per_page=20)
        except Exception:
            with contextlib.suppress(TelegramBadRequest):
                await callback.message.edit_text(
                    i18n.get("feed-respond-fetch-error"), parse_mode="HTML"
                )
            return

        items = data.get("items") or []
        for it in items:
            rid = it.get("id")
            if not rid:
                continue
            resume_ids.append(str(rid))
            title = it.get("title") or rid
            titles.append(str(title)[:60])

    if not resume_ids:
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("feed-respond-no-resumes"), parse_mode="HTML"
            )
        return

    await _send_feed_respond_resume_choice(
        callback.message,
        state,
        feed_session,
        vacancy,
        resume_ids,
        titles,
        i18n,
        show_refresh=settings.hh_ui_apply_enabled,
        respond_mode=respond_mode,
    )


@router.callback_query(FeedCallback.filter(F.action == "respond"))
async def handle_feed_respond(
    callback: CallbackQuery,
    callback_data: FeedCallback,
    session: AsyncSession,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    from src.config import settings

    mode = "letter_then_apply" if settings.hh_ui_apply_enabled else "api"
    await _feed_respond_core(
        callback,
        callback_data,
        session,
        user,
        state,
        i18n,
        respond_mode=mode,
        log_event="feed_respond_click",
    )


@router.callback_query(FeedCallback.filter(F.action == "respond_ai_cover"))
async def handle_feed_respond_ai_cover(
    callback: CallbackQuery,
    callback_data: FeedCallback,
    session: AsyncSession,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    from src.config import settings

    if not settings.hh_ui_apply_enabled:
        await callback.answer(i18n.get("feed-respond-ai-not-available"), show_alert=True)
        return
    await _feed_respond_core(
        callback,
        callback_data,
        session,
        user,
        state,
        i18n,
        respond_mode="ai_chain",
        log_event="feed_respond_ai_click",
    )


@router.callback_query(FeedCallback.filter(F.action == "respond_refresh_resumes"))
async def handle_feed_respond_refresh_resumes(
    callback: CallbackQuery,
    callback_data: FeedCallback,
    session: AsyncSession,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    from src.config import settings
    from src.services.hh.crypto import HhTokenCipher
    from src.services.hh_ui.outcomes import ApplyOutcome
    from src.services.hh_ui.storage import decrypt_browser_storage

    if not settings.hh_ui_apply_enabled:
        await callback.answer()
        return

    if await state.get_state() != FeedRespondForm.choosing_resume.state:
        await callback.answer()
        return

    data = await state.get_data()
    if (
        data.get("feed_session_id") != callback_data.session_id
        or data.get("vacancy_id") != callback_data.vacancy_id
    ):
        await callback.answer(i18n.get("feed-respond-bad-resume"), show_alert=True)
        return

    feed_session = await feed_services.get_feed_session(session, callback_data.session_id)
    if not feed_session or feed_session.is_completed or not feed_session.hh_linked_account_id:
        await callback.answer(i18n.get("feed-session-not-found"), show_alert=True)
        return

    vacancy_repo = AutoparsedVacancyRepository(session)
    vacancy = await vacancy_repo.get_by_id(callback_data.vacancy_id)
    if not vacancy:
        await callback.answer()
        return

    acc_repo = HhLinkedAccountRepository(session)
    acc = await acc_repo.get_by_id(feed_session.hh_linked_account_id)
    if not acc or not acc.browser_storage_enc:
        await callback.answer(i18n.get("feed-respond-no-browser-session"), show_alert=True)
        return

    try:
        cipher = HhTokenCipher(settings.hh_token_encryption_key)
        storage = decrypt_browser_storage(acc.browser_storage_enc, cipher)
    except Exception:
        await callback.answer(i18n.get("hh-token-error"), show_alert=True)
        return
    if not storage:
        await callback.answer(i18n.get("feed-respond-no-browser-session"), show_alert=True)
        return

    await acc_repo.clear_resume_list_cache(acc)
    await session.flush()

    await callback.answer()
    logger.info(
        "feed_respond_resume_cache_refresh",
        user_id=user.id,
        hh_linked_account_id=acc.id,
        vacancy_id=vacancy.id,
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("feed-respond-loading-resumes"),
            parse_mode="HTML",
        )

    try:
        lr = await _run_list_resumes_ui_feed(storage, user.id)
    except asyncio.TimeoutError:
        logger.warning(
            "feed_respond_list_resumes_timeout",
            user_id=user.id,
            vacancy_id=vacancy.id,
            timeout_s=_LIST_RESUMES_TIMEOUT_S,
        )
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("feed-respond-load-timeout"),
                parse_mode="HTML",
            )
        return
    except Exception as exc:
        logger.exception(
            "feed_respond_list_resumes_failed",
            user_id=user.id,
            vacancy_id=vacancy.id,
            error=str(exc),
        )
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("feed-respond-fetch-error"), parse_mode="HTML"
            )
        return

    if lr.outcome == ApplyOutcome.CAPTCHA:
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("feed-respond-ui-captcha"), parse_mode="HTML"
            )
        if lr.screenshot_bytes:
            await callback.message.answer_photo(
                BufferedInputFile(lr.screenshot_bytes, "hh_captcha.png"),
            )
        return
    if lr.outcome == ApplyOutcome.SESSION_EXPIRED:
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("feed-respond-ui-session-expired"), parse_mode="HTML"
            )
        return
    if lr.outcome != ApplyOutcome.SUCCESS or not lr.resumes:
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("feed-respond-fetch-error"), parse_mode="HTML"
            )
        return

    await acc_repo.update_resume_list_cache(
        acc,
        [{"id": r.id, "title": r.title} for r in lr.resumes[:12]],
    )
    await session.commit()

    resume_ids = []
    titles = []
    for r in lr.resumes[:12]:
        resume_ids.append(r.id)
        titles.append(r.title[:60])

    respond_mode = str(data.get("respond_mode") or "letter_then_apply")
    await _send_feed_respond_resume_choice(
        callback.message,
        state,
        feed_session,
        vacancy,
        resume_ids,
        titles,
        i18n,
        show_refresh=True,
        respond_mode=respond_mode,
    )


@router.callback_query(FeedCallback.filter(F.action == "respond_cancel"))
async def handle_feed_respond_cancel(
    callback: CallbackQuery,
    callback_data: FeedCallback,
    session: AsyncSession,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.clear()
    feed_session = await feed_services.get_feed_session(session, callback_data.session_id)
    if not feed_session or feed_session.is_completed:
        await callback.answer()
        return
    vacancy_repo = AutoparsedVacancyRepository(session)
    vacancy = await vacancy_repo.get_by_id(callback_data.vacancy_id)
    if not vacancy:
        await callback.answer()
        return
    total = len(feed_session.vacancy_ids)
    text = feed_services.build_vacancy_card(
        vacancy, feed_session.current_index, total, i18n.locale
    )
    keyboard = feed_vacancy_keyboard(
        feed_session.id, vacancy.id, vacancy.url, i18n,
        current_index=feed_session.current_index,
        show_respond=_feed_show_respond_button(feed_session),
        **_feed_vacancy_keyboard_options(feed_session, vacancy.id),
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(FeedCallback.filter(F.action == "respond_pick"))
async def handle_feed_respond_pick(
    callback: CallbackQuery,
    callback_data: FeedCallback,
    session: AsyncSession,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    from src.config import settings
    from src.core.celery_async import run_celery_task
    from src.services.hh.client import HhApiError, apply_to_vacancy_with_resume
    from src.services.hh.token_service import ensure_access_token
    from src.services.hh_ui.rate_limit import try_acquire_ui_apply_slot_async
    from src.services.hh_ui.runner import normalize_hh_vacancy_url
    from src.worker.tasks.cover_letter import generate_cover_letter_task
    from src.worker.tasks.hh_ui_apply import apply_to_vacancy_ui_task

    data = await state.get_data()
    resume_ids = data.get("resume_ids") or []
    respond_mode = data.get("respond_mode")
    if respond_mode is None:
        respond_mode = "letter_then_apply" if settings.hh_ui_apply_enabled else "api"
    else:
        respond_mode = str(respond_mode)

    idx = callback_data.resume_idx
    if idx < 0 or idx >= len(resume_ids):
        await state.clear()
        await callback.answer(i18n.get("feed-respond-bad-resume"), show_alert=True)
        return

    resume_id = resume_ids[idx]

    feed_session = await feed_services.get_feed_session(session, callback_data.session_id)
    if not feed_session or feed_session.is_completed or not feed_session.hh_linked_account_id:
        await state.clear()
        await callback.answer(i18n.get("feed-session-not-found"), show_alert=True)
        return

    vacancy_repo = AutoparsedVacancyRepository(session)
    vacancy = await vacancy_repo.get_by_id(callback_data.vacancy_id)
    if not vacancy:
        await state.clear()
        await callback.answer()
        return

    if settings.hh_ui_apply_enabled:
        attempt_repo = HhApplicationAttemptRepository(session)
        if await attempt_repo.has_successful_apply(user.id, vacancy.hh_vacancy_id, resume_id):
            await state.clear()
            await callback.answer(i18n.get("feed-respond-ui-already-applied"), show_alert=True)
            return
        if not await try_acquire_ui_apply_slot_async(user.id):
            await state.clear()
            await callback.answer(i18n.get("feed-respond-ui-rate-limited"), show_alert=True)
            return

        if respond_mode == "letter_then_apply":
            await state.set_state(FeedRespondForm.entering_cover_letter)
            await state.update_data(
                feed_session_id=feed_session.id,
                vacancy_id=vacancy.id,
                resume_id=resume_id,
                hh_linked_account_id=feed_session.hh_linked_account_id,
                prompt_message_id=callback.message.message_id,
            )
            await callback.answer()
            with contextlib.suppress(TelegramBadRequest):
                await callback.message.edit_text(
                    i18n.get("feed-respond-enter-letter"),
                    reply_markup=feed_respond_letter_keyboard(
                        feed_session.id, vacancy.id, i18n
                    ),
                    parse_mode="HTML",
                )
            return

        if respond_mode == "ai_chain":
            await state.clear()
            from src.bot.modules.autoparse import services as ap_service

            vacancy_url = normalize_hh_vacancy_url(vacancy.url, vacancy.hh_vacancy_id)
            apply_after = {
                "user_id": user.id,
                "chat_id": callback.message.chat.id,
                "message_id": callback.message.message_id,
                "locale": i18n.locale,
                "hh_linked_account_id": feed_session.hh_linked_account_id,
                "autoparsed_vacancy_id": vacancy.id,
                "hh_vacancy_id": vacancy.hh_vacancy_id,
                "resume_id": resume_id,
                "vacancy_url": vacancy_url,
                "feed_session_id": feed_session.id,
            }
            current = await ap_service.get_user_autoparse_settings(session, user.id)
            cover_letter_style = current.get("cover_letter_style", "professional")
            session_id = feed_session.id
            await feed_services.advance_feed_index(session, feed_session)
            feed_session = await feed_services.get_feed_session(session, session_id)
            if not feed_session:
                await callback.answer(i18n.get("feed-session-not-found"), show_alert=True)
                return
            await _feed_show_next_vacancy_or_results(callback, session, feed_session, i18n)
            await run_celery_task(
                generate_cover_letter_task,
                user.id,
                vacancy.id,
                callback.message.chat.id,
                callback.message.message_id,
                i18n.locale,
                cover_letter_style,
                feed_session.id,
                "feed_respond_apply",
                apply_after=apply_after,
                silent_feed=True,
            )
            return

    await state.clear()

    try:
        _, access = await ensure_access_token(session, feed_session.hh_linked_account_id)
    except Exception:
        await callback.answer(i18n.get("hh-token-error"), show_alert=True)
        return

    from src.services.hh.client import HhApiClient

    await callback.answer()
    client = HhApiClient(access)
    attempt_repo = HhApplicationAttemptRepository(session)
    err_code = None
    neg_id = None
    status = "error"
    excerpt = None
    try:
        _st, body = await apply_to_vacancy_with_resume(
            client,
            vacancy_id=vacancy.hh_vacancy_id,
            resume_id=resume_id,
        )
        status = "success"
        if isinstance(body, dict):
            neg_id = str(body.get("id", "") or "") or None
            excerpt = str(body)[:2000]
    except HhApiError as exc:
        status = "error"
        err_code = str(exc)
        if isinstance(exc.body, dict):
            errs = exc.body.get("errors") or []
            if errs and isinstance(errs[0], dict):
                err_code = str(errs[0].get("value", exc))
        excerpt = str(exc.body)[:2000] if exc.body else str(exc)

    await attempt_repo.create(
        user_id=user.id,
        hh_linked_account_id=feed_session.hh_linked_account_id,
        autoparsed_vacancy_id=vacancy.id,
        hh_vacancy_id=vacancy.hh_vacancy_id,
        resume_id=resume_id,
        status=status,
        api_negotiation_id=neg_id,
        error_code=err_code,
        response_excerpt=excerpt,
    )
    await session.commit()

    if status != "success":
        await feed_services.remove_liked_on_apply_failure(
            session, feed_session.id, vacancy.id
        )
        feed_session = await feed_services.get_feed_session(session, feed_session.id) or feed_session

    total = len(feed_session.vacancy_ids)
    text = feed_services.build_vacancy_card(
        vacancy, feed_session.current_index, total, i18n.locale
    )
    if status == "success":
        text = f"{text}\n\n{i18n.get('feed-respond-success')}"
    else:
        text = f"{text}\n\n{i18n.get('feed-respond-error', detail=err_code or 'error')}"

    keyboard = feed_vacancy_keyboard(
        feed_session.id, vacancy.id, vacancy.url, i18n,
        current_index=feed_session.current_index,
        show_respond=_feed_show_respond_button(feed_session),
        **_feed_vacancy_keyboard_options(feed_session, vacancy.id),
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


async def _feed_letter_state_guard(
    state: FSMContext,
    callback_data: FeedCallback,
) -> dict | None:
    """Return FSM data if entering_cover_letter matches callback; else None."""
    st = await state.get_state()
    if st != FeedRespondForm.entering_cover_letter.state:
        return None
    data = await state.get_data()
    if (
        data.get("feed_session_id") != callback_data.session_id
        or data.get("vacancy_id") != callback_data.vacancy_id
    ):
        return None
    return data


@router.callback_query(FeedCallback.filter(F.action == "respond_letter_skip"))
async def handle_feed_respond_letter_skip(
    callback: CallbackQuery,
    callback_data: FeedCallback,
    session: AsyncSession,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    from src.config import settings
    from src.core.celery_async import run_celery_task
    from src.services.hh_ui.rate_limit import try_acquire_ui_apply_slot_async
    from src.services.hh_ui.runner import normalize_hh_vacancy_url
    from src.worker.tasks.hh_ui_apply import apply_to_vacancy_ui_task

    data = await _feed_letter_state_guard(state, callback_data)
    if not data:
        await callback.answer(i18n.get("feed-respond-session-expired"), show_alert=True)
        return

    resume_id = str(data.get("resume_id") or "")
    feed_session = await feed_services.get_feed_session(session, data["feed_session_id"])
    if not feed_session or feed_session.is_completed or not feed_session.hh_linked_account_id:
        await state.clear()
        await callback.answer(i18n.get("feed-session-not-found"), show_alert=True)
        return

    vacancy_repo = AutoparsedVacancyRepository(session)
    vacancy = await vacancy_repo.get_by_id(int(data["vacancy_id"]))
    if not vacancy:
        await state.clear()
        await callback.answer()
        return

    if not settings.hh_ui_apply_enabled:
        await state.clear()
        await callback.answer()
        return

    attempt_repo = HhApplicationAttemptRepository(session)
    if await attempt_repo.has_successful_apply(user.id, vacancy.hh_vacancy_id, resume_id):
        await state.clear()
        await callback.answer(i18n.get("feed-respond-ui-already-applied"), show_alert=True)
        return
    if not await try_acquire_ui_apply_slot_async(user.id):
        await state.clear()
        await callback.answer(i18n.get("feed-respond-ui-rate-limited"), show_alert=True)
        return

    vacancy_url = normalize_hh_vacancy_url(vacancy.url, vacancy.hh_vacancy_id)
    await state.clear()
    await callback.answer()
    await run_celery_task(
        apply_to_vacancy_ui_task,
        user.id,
        callback.message.chat.id,
        callback.message.message_id,
        i18n.locale,
        feed_session.hh_linked_account_id,
        vacancy.id,
        vacancy.hh_vacancy_id,
        resume_id,
        vacancy_url,
        feed_session.id,
        "",
    )
    total = len(feed_session.vacancy_ids)
    text = feed_services.build_vacancy_card(
        vacancy, feed_session.current_index, total, i18n.locale
    )
    text = f"{text}\n\n{i18n.get('feed-respond-ui-queued')}"
    keyboard = feed_vacancy_keyboard(
        feed_session.id, vacancy.id, vacancy.url, i18n,
        current_index=feed_session.current_index,
        show_respond=_feed_show_respond_button(feed_session),
        **_feed_vacancy_keyboard_options(feed_session, vacancy.id),
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(FeedCallback.filter(F.action == "respond_letter_generate"))
async def handle_feed_respond_letter_generate(
    callback: CallbackQuery,
    callback_data: FeedCallback,
    session: AsyncSession,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    from src.config import settings
    from src.core.celery_async import run_celery_task
    from src.services.hh_ui.rate_limit import try_acquire_ui_apply_slot_async
    from src.services.hh_ui.runner import normalize_hh_vacancy_url
    from src.worker.tasks.cover_letter import generate_cover_letter_task

    data = await _feed_letter_state_guard(state, callback_data)
    if not data:
        await callback.answer(i18n.get("feed-respond-session-expired"), show_alert=True)
        return

    resume_id = str(data.get("resume_id") or "")
    feed_session = await feed_services.get_feed_session(session, data["feed_session_id"])
    if not feed_session or feed_session.is_completed or not feed_session.hh_linked_account_id:
        await state.clear()
        await callback.answer(i18n.get("feed-session-not-found"), show_alert=True)
        return

    vacancy_repo = AutoparsedVacancyRepository(session)
    vacancy = await vacancy_repo.get_by_id(int(data["vacancy_id"]))
    if not vacancy:
        await state.clear()
        await callback.answer()
        return

    if not settings.hh_ui_apply_enabled:
        await state.clear()
        await callback.answer()
        return

    attempt_repo = HhApplicationAttemptRepository(session)
    if await attempt_repo.has_successful_apply(user.id, vacancy.hh_vacancy_id, resume_id):
        await state.clear()
        await callback.answer(i18n.get("feed-respond-ui-already-applied"), show_alert=True)
        return
    if not await try_acquire_ui_apply_slot_async(user.id):
        await state.clear()
        await callback.answer(i18n.get("feed-respond-ui-rate-limited"), show_alert=True)
        return

    vacancy_url = normalize_hh_vacancy_url(vacancy.url, vacancy.hh_vacancy_id)
    apply_after = {
        "user_id": user.id,
        "chat_id": callback.message.chat.id,
        "message_id": callback.message.message_id,
        "locale": i18n.locale,
        "hh_linked_account_id": feed_session.hh_linked_account_id,
        "autoparsed_vacancy_id": vacancy.id,
        "hh_vacancy_id": vacancy.hh_vacancy_id,
        "resume_id": resume_id,
        "vacancy_url": vacancy_url,
        "feed_session_id": feed_session.id,
    }
    from src.bot.modules.autoparse import services as ap_service

    current = await ap_service.get_user_autoparse_settings(session, user.id)
    cover_letter_style = current.get("cover_letter_style", "professional")
    await state.clear()
    await callback.answer()
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("feed-cover-letter-generating"),
            parse_mode="HTML",
        )
    await run_celery_task(
        generate_cover_letter_task,
        user.id,
        vacancy.id,
        callback.message.chat.id,
        callback.message.message_id,
        i18n.locale,
        cover_letter_style,
        feed_session.id,
        "feed_respond_apply",
        apply_after=apply_after,
    )


@router.message(FeedRespondForm.entering_cover_letter, F.text)
async def handle_feed_respond_letter_paste(
    message: Message,
    session: AsyncSession,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    from src.config import settings
    from src.core.celery_async import run_celery_task
    from src.services.hh_ui.rate_limit import try_acquire_ui_apply_slot_async
    from src.services.hh_ui.runner import normalize_hh_vacancy_url
    from src.worker.tasks.hh_ui_apply import apply_to_vacancy_ui_task

    data = await state.get_data()
    feed_session_id = data.get("feed_session_id")
    vacancy_id = data.get("vacancy_id")
    resume_id = str(data.get("resume_id") or "")
    prompt_message_id = data.get("prompt_message_id")
    if feed_session_id is None or vacancy_id is None or not resume_id:
        await state.clear()
        return

    feed_session = await feed_services.get_feed_session(session, int(feed_session_id))
    if not feed_session or feed_session.is_completed or not feed_session.hh_linked_account_id:
        await state.clear()
        return

    vacancy_repo = AutoparsedVacancyRepository(session)
    vacancy = await vacancy_repo.get_by_id(int(vacancy_id))
    if not vacancy:
        await state.clear()
        return

    if not settings.hh_ui_apply_enabled:
        await state.clear()
        return

    letter = (message.text or "").strip()
    attempt_repo = HhApplicationAttemptRepository(session)
    if await attempt_repo.has_successful_apply(user.id, vacancy.hh_vacancy_id, resume_id):
        await state.clear()
        return
    if not await try_acquire_ui_apply_slot_async(user.id):
        await state.clear()
        return

    vacancy_url = normalize_hh_vacancy_url(vacancy.url, vacancy.hh_vacancy_id)
    await state.clear()
    await run_celery_task(
        apply_to_vacancy_ui_task,
        user.id,
        message.chat.id,
        int(prompt_message_id) if prompt_message_id is not None else message.message_id,
        i18n.locale,
        feed_session.hh_linked_account_id,
        vacancy.id,
        vacancy.hh_vacancy_id,
        resume_id,
        vacancy_url,
        feed_session.id,
        letter,
    )
    total = len(feed_session.vacancy_ids)
    text = feed_services.build_vacancy_card(
        vacancy, feed_session.current_index, total, i18n.locale
    )
    text = f"{text}\n\n{i18n.get('feed-respond-ui-queued')}"
    keyboard = feed_vacancy_keyboard(
        feed_session.id, vacancy.id, vacancy.url, i18n,
        current_index=feed_session.current_index,
        show_respond=_feed_show_respond_button(feed_session),
        **_feed_vacancy_keyboard_options(feed_session, vacancy.id),
    )
    edit_id = int(prompt_message_id) if prompt_message_id is not None else message.message_id
    with contextlib.suppress(TelegramBadRequest):
        await message.bot.edit_message_text(
            text,
            chat_id=message.chat.id,
            message_id=edit_id,
            reply_markup=keyboard,
            parse_mode="HTML",
        )


@router.callback_query(FeedCallback.filter(F.action == "stop"))
async def handle_feed_stop(
    callback: CallbackQuery,
    callback_data: FeedCallback,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    feed_session = await feed_services.get_feed_session(session, callback_data.session_id)
    if not feed_session:
        await callback.answer()
        return
    await _show_results(callback, session, feed_session, i18n)


async def _show_results(
    callback: CallbackQuery,
    session: AsyncSession,
    feed_session: VacancyFeedSession,
    i18n: I18nContext,
) -> None:
    if not feed_session.is_completed:
        await feed_services.complete_feed_session(session, feed_session)

    vacancy_repo = AutoparsedVacancyRepository(session)
    liked_vacancies = []
    for vid in feed_session.liked_ids:
        vacancy = await vacancy_repo.get_by_id(vid)
        if vacancy:
            liked_vacancies.append(vacancy)

    vacancies_by_id = {v.id: v for v in liked_vacancies}
    results = feed_services.compute_feed_results(feed_session, vacancies_by_id)

    ui_apply_lines: list[str] = []
    since = getattr(feed_session, "created_at", None)
    if isinstance(since, datetime):
        attempt_repo = HhApplicationAttemptRepository(session)
        attempts = await attempt_repo.list_for_feed_session_summary(
            user_id=feed_session.user_id,
            vacancy_ids=list(feed_session.vacancy_ids),
            since=since,
        )
        attempts_sorted = sorted(attempts, key=lambda a: a.created_at)
        for a in attempts_sorted:
            vid = a.autoparsed_vacancy_id
            if vid is None:
                title = "?"
            else:
                v = await vacancy_repo.get_by_id(vid)
                title = v.title if v else f"#{vid}"
            ok = a.status == "success"
            detail = None if ok else (a.error_code or a.status or "")
            ui_apply_lines.append(
                feed_services.format_ui_apply_result_line(
                    title,
                    success=ok,
                    detail=detail,
                    status=a.status,
                    locale=i18n.locale,
                )
            )

    text = feed_services.build_results_message(
        results,
        i18n.locale,
        ui_apply_lines=ui_apply_lines or None,
    )

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=None, parse_mode="HTML")
    await callback.answer()
