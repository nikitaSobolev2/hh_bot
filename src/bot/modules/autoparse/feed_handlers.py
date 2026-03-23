"""Handlers for the interactive vacancy feed."""

from __future__ import annotations

import asyncio
import contextlib

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.modules.autoparse import feed_services
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


def feed_vacancy_keyboard(
    session_id: int,
    vacancy_id: int,
    vacancy_url: str,
    i18n: I18nContext,
    mode: str = "summary",
    *,
    current_index: int = 0,
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
                text=i18n.get("feed-btn-fits-me"),
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
        rows.append(
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
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=AutoparseCallback(action="hub").pack(),
                )
            ]
        )
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
        else:
            await callback.answer(i18n.get("feed-no-hh-link"), show_alert=True)
            return

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
    from src.services.hh.client import HhApiClient
    from src.services.hh.crypto import HhTokenCipher
    from src.services.hh.token_service import ensure_access_token
    from src.services.hh_ui.config import HhUiApplyConfig
    from src.services.hh_ui.outcomes import ApplyOutcome
    from src.services.hh_ui.runner import list_resumes_ui
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
        await callback.answer()
        return

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
        # Telegram callback must be answered within ~10s; list_resumes_ui can take longer.
        await callback.answer()
        cfg = HhUiApplyConfig.from_settings()
        try:
            lr = await asyncio.to_thread(list_resumes_ui, storage_state=storage, config=cfg)
        except Exception:
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

    await state.set_state(FeedRespondForm.choosing_resume)
    await state.update_data(
        feed_session_id=feed_session.id,
        vacancy_id=vacancy.id,
        resume_ids=resume_ids,
    )

    rows: list[list[InlineKeyboardButton]] = []
    for idx, title in enumerate(titles[:12]):
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{idx + 1}. {title}"[:64],
                    callback_data=FeedCallback(
                        action="respond_pick",
                        session_id=feed_session.id,
                        vacancy_id=vacancy.id,
                        resume_idx=idx,
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
                    session_id=feed_session.id,
                    vacancy_id=vacancy.id,
                ).pack(),
            )
        ]
    )
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("feed-respond-pick-resume"),
            reply_markup=kb,
            parse_mode="HTML",
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
    from src.services.hh_ui.runner import normalize_hh_vacancy_url
    from src.worker.tasks.hh_ui_apply import apply_to_vacancy_ui_task

    data = await state.get_data()
    resume_ids = data.get("resume_ids") or []
    await state.clear()

    idx = callback_data.resume_idx
    if idx < 0 or idx >= len(resume_ids):
        await callback.answer(i18n.get("feed-respond-bad-resume"), show_alert=True)
        return

    resume_id = resume_ids[idx]

    feed_session = await feed_services.get_feed_session(session, callback_data.session_id)
    if not feed_session or feed_session.is_completed or not feed_session.hh_linked_account_id:
        await callback.answer(i18n.get("feed-session-not-found"), show_alert=True)
        return

    vacancy_repo = AutoparsedVacancyRepository(session)
    vacancy = await vacancy_repo.get_by_id(callback_data.vacancy_id)
    if not vacancy:
        await callback.answer()
        return

    if settings.hh_ui_apply_enabled:
        attempt_repo = HhApplicationAttemptRepository(session)
        if await attempt_repo.has_successful_apply(user.id, vacancy.hh_vacancy_id, resume_id):
            await callback.answer(i18n.get("feed-respond-ui-already-applied"), show_alert=True)
            return
        from src.services.hh_ui.rate_limit import try_acquire_ui_apply_slot_async

        if not await try_acquire_ui_apply_slot_async(user.id):
            await callback.answer(i18n.get("feed-respond-ui-rate-limited"), show_alert=True)
            return

        vacancy_url = normalize_hh_vacancy_url(vacancy.url, vacancy.hh_vacancy_id)
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
        )
        total = len(feed_session.vacancy_ids)
        text = feed_services.build_vacancy_card(
            vacancy, feed_session.current_index, total, i18n.locale
        )
        text = f"{text}\n\n{i18n.get('feed-respond-ui-queued')}"
        keyboard = feed_vacancy_keyboard(
            feed_session.id, vacancy.id, vacancy.url, i18n,
            current_index=feed_session.current_index,
        )
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        return

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
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


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
    text = feed_services.build_results_message(results, i18n.locale)

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=None, parse_mode="HTML")
    await callback.answer()
