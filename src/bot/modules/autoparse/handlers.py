"""Handlers for the Autoparse feature."""

import contextlib
from datetime import UTC, datetime, timedelta

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.modules.autoparse import services as ap_service
from src.bot.modules.autoparse.callbacks import (
    AutoparseCallback,
    AutoparseDownloadCallback,
    AutoparseSettingsCallback,
)
from src.bot.modules.autoparse.autorespond_handlers import (
    autorespond_globally_enabled,
    router as autorespond_router,
)
from src.bot.modules.autoparse.feed_handlers import router as feed_router
from src.bot.modules.autoparse.keyboards import (
    autoparse_detail_keyboard,
    autoparse_hub_keyboard,
    autoparse_list_keyboard,
    autoparse_settings_keyboard,
    cancel_keyboard,
    confirm_delete_keyboard,
    cover_letter_style_keyboard,
    download_format_keyboard,
    include_reacted_keyboard,
    liked_disliked_list_keyboard,
    target_count_select_keyboard,
    template_list_keyboard,
)
from src.bot.modules.autoparse.states import AutoparseEditForm, AutoparseForm, AutoparseSettingsForm
from src.bot.modules.parsing import services as parsing_service
from src.bot.utils.limits import get_min_compat_range
from src.core.i18n import I18nContext
from src.models.autoparse import AutoparseCompany
from src.models.user import User
from src.repositories.app_settings import AppSettingRepository
from src.repositories.autoparse import AutoparsedVacancyRepository
from src.repositories.hh_linked_account import HhLinkedAccountRepository
from src.repositories.parsing import ParsingCompanyRepository
from src.repositories.vacancy_feed import VacancyFeedSessionRepository

router = Router(name="autoparse")
router.include_router(feed_router)
router.include_router(autorespond_router)

_PER_PAGE = 5
_VACANCIES_PER_PAGE = 15


async def _has_tech_stack(session: AsyncSession, user_id: int) -> bool:
    """Return True if the user already has a tech stack (manual or from work experience)."""
    settings = await ap_service.get_user_autoparse_settings(session, user_id)
    if settings.get("tech_stack"):
        return True
    experiences = await parsing_service.get_active_work_experiences(session, user_id)
    return bool(experiences)


async def _user_has_hh_browser_session(session: AsyncSession, user_id: int) -> bool:
    """True if the user has at least one HH account with saved Playwright storage."""
    hh_repo = HhLinkedAccountRepository(session)
    accs = await hh_repo.list_active_for_user(user_id)
    return any(a.browser_storage_enc for a in accs)


async def _resolve_hh_linked_account_for_negotiations_sync(
    session: AsyncSession,
    user: User,
    company: AutoparseCompany,
) -> int | None:
    """Prefer company autorespond HH account; else first linked account with browser storage."""
    hh_repo = HhLinkedAccountRepository(session)
    if company.autorespond_hh_linked_account_id:
        acc = await hh_repo.get_by_id(company.autorespond_hh_linked_account_id)
        if acc and acc.user_id == user.id and acc.browser_storage_enc:
            return acc.id
    accs = await hh_repo.list_active_for_user(user.id)
    for a in accs:
        if a.browser_storage_enc:
            return a.id
    return None


async def _should_show_run_now(
    session: AsyncSession, company: AutoparseCompany, user: User
) -> bool:
    """Return True if the manual 'Run now' button should be shown for this company."""
    if user.is_admin:
        return company.is_enabled
    if not company.is_enabled:
        return False
    settings_repo = AppSettingRepository(session)
    interval_hours = int(await settings_repo.get_value("autoparse_interval_hours", default=6))
    if company.last_parsed_at is None:
        return True
    elapsed = datetime.now(UTC).replace(tzinfo=None) - company.last_parsed_at
    return elapsed > timedelta(hours=interval_hours)


# ── Hub ─────────────────────────────────────────────────────────────


async def show_autoparse_hub(callback: CallbackQuery, i18n: I18nContext) -> None:
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            f"<b>{i18n.get('autoparse-hub-title')}</b>\n\n{i18n.get('autoparse-hub-subtitle')}",
            reply_markup=autoparse_hub_keyboard(i18n),
        )


@router.callback_query(AutoparseCallback.filter(F.action == "hub"))
async def hub_handler(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.clear()
    await show_autoparse_hub(callback, i18n)
    await callback.answer()


# ── Create flow ─────────────────────────────────────────────────────


@router.callback_query(AutoparseCallback.filter(F.action == "create"))
async def create_start(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    page = callback_data.page
    repo = ParsingCompanyRepository(session)
    companies = await repo.get_by_user(user.id, offset=page * _PER_PAGE, limit=_PER_PAGE + 1)
    has_more = len(companies) > _PER_PAGE
    display = companies[:_PER_PAGE]

    await state.set_state(AutoparseForm.select_template)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("autoparse-select-template"),
            reply_markup=template_list_keyboard(display, page, has_more, i18n),
        )
    await callback.answer()


@router.callback_query(AutoparseCallback.filter(F.action == "template_select"))
async def template_selected(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    repo = ParsingCompanyRepository(session)
    company = await repo.get_by_id(callback_data.company_id)
    if not company:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return

    await state.update_data(
        vacancy_title=company.vacancy_title,
        search_url=company.search_url,
        keyword_filter=company.keyword_filter,
        skills="",
    )

    if await _has_tech_stack(session, user.id):
        await state.set_state(AutoparseForm.include_reacted)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("autoparse-include-reacted-prompt"),
                reply_markup=include_reacted_keyboard(i18n),
            )
        await callback.answer()
        return

    await state.set_state(AutoparseForm.skills)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("autoparse-enter-skills"),
            reply_markup=cancel_keyboard(i18n),
        )
    await callback.answer()


@router.callback_query(AutoparseCallback.filter(F.action == "skip_template"))
async def skip_template(callback: CallbackQuery, state: FSMContext, i18n: I18nContext) -> None:
    await state.set_state(AutoparseForm.vacancy_title)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("autoparse-enter-title"),
            reply_markup=cancel_keyboard(i18n),
        )
    await callback.answer()


@router.message(AutoparseForm.vacancy_title)
async def receive_title(message: Message, state: FSMContext, i18n: I18nContext) -> None:
    await state.update_data(vacancy_title=message.text.strip())
    await state.set_state(AutoparseForm.search_url)
    await message.answer(
        i18n.get("autoparse-enter-url"),
        reply_markup=cancel_keyboard(i18n),
    )


@router.message(AutoparseForm.search_url)
async def receive_url(message: Message, state: FSMContext, i18n: I18nContext) -> None:
    url = message.text.strip()
    if not url.startswith("http"):
        await message.answer(i18n.get("autoparse-enter-url"))
        return
    await state.update_data(search_url=url)
    await state.set_state(AutoparseForm.keyword_filter)
    await message.answer(
        i18n.get("autoparse-enter-keywords"),
        reply_markup=cancel_keyboard(i18n),
    )


@router.message(AutoparseForm.keyword_filter)
async def receive_keywords(
    message: Message, state: FSMContext, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    await state.update_data(keyword_filter=message.text.strip(), skills="")

    if await _has_tech_stack(session, user.id):
        await state.set_state(AutoparseForm.include_reacted)
        await message.answer(
            i18n.get("autoparse-include-reacted-prompt"),
            reply_markup=include_reacted_keyboard(i18n),
        )
        return

    await state.set_state(AutoparseForm.skills)
    await message.answer(
        i18n.get("autoparse-enter-skills"),
        reply_markup=cancel_keyboard(i18n),
    )


@router.message(AutoparseForm.skills)
async def receive_skills(
    message: Message,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.update_data(skills=message.text.strip())
    await state.set_state(AutoparseForm.include_reacted)
    await message.answer(
        i18n.get("autoparse-include-reacted-prompt"),
        reply_markup=include_reacted_keyboard(i18n),
    )


@router.callback_query(
    AutoparseCallback.filter(F.action.in_({"include_reacted_yes", "include_reacted_no"}))
)
async def include_reacted_selected(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    include_reacted = callback_data.action == "include_reacted_yes"

    company = await ap_service.create_autoparse_company(
        session,
        user.id,
        data["vacancy_title"],
        data["search_url"],
        data.get("keyword_filter", ""),
        data.get("skills", ""),
        include_reacted_in_feed=include_reacted,
    )
    await state.clear()
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("autoparse-created-success", id=str(company.id)),
            reply_markup=autoparse_hub_keyboard(i18n),
        )
    await callback.answer()


# ── List ────────────────────────────────────────────────────────────


@router.callback_query(AutoparseCallback.filter(F.action == "list"))
async def list_companies(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    page = callback_data.page
    companies, total = await ap_service.get_user_autoparse_companies(
        session, user.id, page, _PER_PAGE
    )
    if not companies and page == 0:
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("autoparse-empty-list"),
                reply_markup=autoparse_hub_keyboard(i18n),
            )
        await callback.answer()
        return

    has_more = (page + 1) * _PER_PAGE < total
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("autoparse-list-title"),
            reply_markup=autoparse_list_keyboard(companies, page, has_more, i18n),
        )
    await callback.answer()


@router.callback_query(AutoparseCallback.filter(F.action == "show_liked"))
async def show_liked_vacancies(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await callback.answer()
    feed_repo = VacancyFeedSessionRepository(session)
    vacancy_repo = AutoparsedVacancyRepository(session)
    liked_ids = await feed_repo.get_all_liked_vacancy_ids_for_user(user.id)
    if not liked_ids:
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("autoparse-liked-empty"),
                reply_markup=liked_disliked_list_keyboard(
                    "show_liked", 0, False, i18n
                ),
            )
        return

    ids_list = sorted(liked_ids, reverse=True)
    page = callback_data.page
    start = page * _VACANCIES_PER_PAGE
    page_ids = ids_list[start : start + _VACANCIES_PER_PAGE]
    has_more = start + _VACANCIES_PER_PAGE < len(ids_list)

    vacancies = await vacancy_repo.get_by_ids_simple(page_ids)
    order = {vid: i for i, vid in enumerate(page_ids)}
    vacancies_sorted = sorted(vacancies, key=lambda v: order.get(v.id, 999))

    lines = [f"<b>{i18n.get('autoparse-btn-show-liked')}</b> ({len(liked_ids)})\n"]
    for i, v in enumerate(vacancies_sorted, start=start + 1):
        safe_title = v.title.replace("<", "&lt;").replace(">", "&gt;")
        lines.append(f"{i}. <a href='{v.url}'>{safe_title}</a>")
    text = "\n".join(lines)

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=liked_disliked_list_keyboard(
                "show_liked", page, has_more, i18n
            ),
            parse_mode="HTML",
        )


@router.callback_query(AutoparseCallback.filter(F.action == "show_disliked"))
async def show_disliked_vacancies(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await callback.answer()
    feed_repo = VacancyFeedSessionRepository(session)
    vacancy_repo = AutoparsedVacancyRepository(session)
    disliked_ids = await feed_repo.get_all_disliked_vacancy_ids_for_user(user.id)
    if not disliked_ids:
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("autoparse-disliked-empty"),
                reply_markup=liked_disliked_list_keyboard(
                    "show_disliked", 0, False, i18n
                ),
            )
        return

    ids_list = sorted(disliked_ids, reverse=True)
    page = callback_data.page
    start = page * _VACANCIES_PER_PAGE
    page_ids = ids_list[start : start + _VACANCIES_PER_PAGE]
    has_more = start + _VACANCIES_PER_PAGE < len(ids_list)

    vacancies = await vacancy_repo.get_by_ids_simple(page_ids)
    order = {vid: i for i, vid in enumerate(page_ids)}
    vacancies_sorted = sorted(vacancies, key=lambda v: order.get(v.id, 999))

    lines = [f"<b>{i18n.get('autoparse-btn-show-disliked')}</b> ({len(disliked_ids)})\n"]
    for i, v in enumerate(vacancies_sorted, start=start + 1):
        safe_title = v.title.replace("<", "&lt;").replace(">", "&gt;")
        lines.append(f"{i}. <a href='{v.url}'>{safe_title}</a>")
    text = "\n".join(lines)

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=liked_disliked_list_keyboard(
                "show_disliked", page, has_more, i18n
            ),
            parse_mode="HTML",
        )


@router.callback_query(AutoparseCallback.filter(F.action == "update_compat_unseen"))
async def handle_update_compat_unseen(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    settings = await ap_service.get_user_autoparse_settings(session, user.id)
    experiences = await parsing_service.get_active_work_experiences(session, user.id)
    has_tech_stack = bool(settings.get("tech_stack")) or bool(experiences)
    if not has_tech_stack:
        await callback.answer(
            i18n.get("autoparse-update-compat-no-tech-stack"),
            show_alert=True,
        )
        return
    from src.core.celery_async import run_celery_task
    from src.worker.tasks.autoparse import update_compatibility_unseen_vacancies

    await run_celery_task(update_compatibility_unseen_vacancies, user.id)
    await callback.answer(i18n.get("autoparse-update-compat-started"), show_alert=True)


@router.callback_query(AutoparseCallback.filter(F.action == "view_feed_below_compat"))
async def handle_view_feed_below_compat(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await callback.answer()
    settings = await ap_service.get_user_autoparse_settings(session, user.id)
    min_compat = float(settings.get("min_compatibility_percent", 50))
    reacted_ids = await ap_service.get_reacted_vacancy_ids_for_user(session, user.id)

    vacancy_repo = AutoparsedVacancyRepository(session)
    vacancies = await vacancy_repo.get_below_min_compat_for_user(
        user.id, min_compat, reacted_ids
    )
    companies, total = await ap_service.get_user_autoparse_companies(
        session, user.id, page=0, per_page=_PER_PAGE
    )
    has_more = total > _PER_PAGE

    if not vacancies:
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("autoparse-feed-below-compat-empty"),
                reply_markup=autoparse_list_keyboard(companies, 0, has_more, i18n),
            )
        return

    companies_for_feed, _ = await ap_service.get_user_autoparse_companies(
        session, user.id, page=0, per_page=1
    )
    first_company_id = companies_for_feed[0].id if companies_for_feed else 0
    if first_company_id == 0:
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("autoparse-feed-below-compat-empty"),
                reply_markup=autoparse_hub_keyboard(i18n),
            )
        return

    from src.bot.modules.autoparse.callbacks import FeedCallback
    from src.bot.modules.autoparse.feed_services import build_stats_message
    from src.repositories.vacancy_feed import VacancyFeedSessionRepository
    from src.services.hh.feed_gating import HhFeedAccountStatus, classify_user_hh_accounts

    hh_status, hh_accounts = await classify_user_hh_accounts(session, user.id)
    hh_linked_id = hh_accounts[0].id if hh_status == HhFeedAccountStatus.SINGLE else None

    feed_repo = VacancyFeedSessionRepository(session)
    feed_session = await feed_repo.create(
        user_id=user.id,
        autoparse_company_id=first_company_id,
        chat_id=user.telegram_id,
        vacancy_ids=[v.id for v in vacancies],
        hh_linked_account_id=hh_linked_id,
        current_index=0,
        liked_ids=[],
        disliked_ids=[],
        is_completed=False,
    )
    await session.commit()

    compat_scores = [v.compatibility_score for v in vacancies if v.compatibility_score is not None]
    avg_compat = sum(compat_scores) / len(compat_scores) if compat_scores else None
    title = i18n.get("autoparse-feed-below-compat-title")
    text = build_stats_message(title, len(vacancies), avg_compat, i18n.locale)

    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    if len(hh_accounts) > 1:
        text = f"{text}\n\n{i18n.get('feed-pick-hh-hint')}"
        rows: list[list[InlineKeyboardButton]] = []
        for acc in hh_accounts:
            label = (acc.label or acc.hh_user_id)[:40]
            rows.append(
                [
                    InlineKeyboardButton(
                        text=label,
                        callback_data=FeedCallback(
                            action="pick_hh_account",
                            session_id=feed_session.id,
                            hh_account_id=acc.id,
                        ).pack(),
                    )
                ]
            )
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=AutoparseCallback(action="list").pack(),
                )
            ]
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    else:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=i18n.get("feed-btn-start"),
                        callback_data=FeedCallback(
                            action="start", session_id=feed_session.id
                        ).pack(),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=i18n.get("feed-btn-stop"),
                        callback_data=FeedCallback(
                            action="stop", session_id=feed_session.id
                        ).pack(),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=i18n.get("btn-back"),
                        callback_data=AutoparseCallback(action="list").pack(),
                    )
                ],
            ]
        )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )


# ── Detail ──────────────────────────────────────────────────────────


@router.callback_query(AutoparseCallback.filter(F.action == "detail"))
async def company_detail(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    company = await ap_service.get_autoparse_detail(session, callback_data.company_id)
    if not company:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return

    count = await ap_service.get_vacancy_count(session, company.id)
    show_run_now = await _should_show_run_now(session, company, user)
    ar_task_on = await autorespond_globally_enabled(session)
    show_sync = await _user_has_hh_browser_session(session, user.id)
    text = ap_service.format_company_detail(
        company,
        count,
        i18n,
        autorespond_global=True,
        autorespond_task_enabled=ar_task_on,
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=autoparse_detail_keyboard(
                company,
                i18n,
                show_run_now=show_run_now,
                show_show_now=(count > 0),
                show_autorespond=True,
                show_sync_negotiations=show_sync,
            ),
        )
    await callback.answer()


@router.callback_query(AutoparseCallback.filter(F.action == "sync_negotiations"))
async def sync_negotiations_with_app(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.core.celery_async import run_celery_task
    from src.worker.tasks.negotiations_sync import sync_negotiations_from_hh_task

    company = await ap_service.get_autoparse_detail(session, callback_data.company_id)
    if not company or company.user_id != user.id:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return
    hh_id = await _resolve_hh_linked_account_for_negotiations_sync(session, user, company)
    if not hh_id:
        await callback.answer(i18n.get("autoparse-sync-error-no-session"), show_alert=True)
        return
    await run_celery_task(
        sync_negotiations_from_hh_task,
        user.id,
        hh_id,
        company.id,
        callback.message.chat.id,
        i18n.locale,
    )
    await callback.answer(i18n.get("autoparse-sync-queued"))


# ── Edit keywords ───────────────────────────────────────────────────


@router.callback_query(AutoparseCallback.filter(F.action == "edit_keywords"))
async def edit_keywords_start(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    company = await ap_service.get_autoparse_detail(session, callback_data.company_id)
    if not company or company.user_id != user.id:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return

    await state.set_state(AutoparseEditForm.edit_keywords)
    await state.update_data(
        edit_keywords_company_id=company.id,
        edit_keywords_message_id=callback.message.message_id,
    )
    current = company.keyword_filter or i18n.get("detail-filter-none")
    await callback.message.answer(
        i18n.get("autoparse-edit-keywords-prompt", current=current),
        reply_markup=cancel_keyboard(i18n),
    )
    await callback.answer()


@router.message(AutoparseEditForm.edit_keywords, F.text)
async def edit_keywords_receive(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    company_id = data.get("edit_keywords_company_id")
    detail_message_id = data.get("edit_keywords_message_id")
    await state.clear()

    if not company_id:
        await message.answer(i18n.get("autoparse-not-found"))
        return

    from src.repositories.autoparse import AutoparseCompanyRepository

    repo = AutoparseCompanyRepository(session)
    company = await repo.get_by_id(company_id)
    if not company or company.user_id != user.id:
        await message.answer(i18n.get("autoparse-not-found"))
        return

    await repo.update(company, keyword_filter=message.text.strip())
    await session.commit()

    count = await ap_service.get_vacancy_count(session, company.id)
    show_run_now = await _should_show_run_now(session, company, user)
    ar_task_on = await autorespond_globally_enabled(session)
    show_sync = await _user_has_hh_browser_session(session, user.id)
    text = ap_service.format_company_detail(
        company,
        count,
        i18n,
        autorespond_global=True,
        autorespond_task_enabled=ar_task_on,
    )
    with contextlib.suppress(TelegramBadRequest):
        await message.bot.edit_message_text(
            text,
            chat_id=message.chat.id,
            message_id=detail_message_id,
            reply_markup=autoparse_detail_keyboard(
                company,
                i18n,
                show_run_now=show_run_now,
                show_show_now=(count > 0),
                show_autorespond=True,
                show_sync_negotiations=show_sync,
            ),
        )
    await message.answer(i18n.get("autoparse-edit-keywords-saved"))


# ── Toggle ──────────────────────────────────────────────────────────


@router.callback_query(AutoparseCallback.filter(F.action == "toggle"))
async def toggle_company(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    new_state = await ap_service.toggle_autoparse_company(session, callback_data.company_id)
    msg = (
        i18n.get("autoparse-toggle-enabled") if new_state else i18n.get("autoparse-toggle-disabled")
    )
    await callback.answer(msg, show_alert=True)

    company = await ap_service.get_autoparse_detail(session, callback_data.company_id)
    if company:
        count = await ap_service.get_vacancy_count(session, company.id)
        show_run_now = await _should_show_run_now(session, company, user)
        ar_task_on = await autorespond_globally_enabled(session)
        show_sync = await _user_has_hh_browser_session(session, user.id)
        text = ap_service.format_company_detail(
            company,
            count,
            i18n,
            autorespond_global=True,
            autorespond_task_enabled=ar_task_on,
        )
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                text,
                reply_markup=autoparse_detail_keyboard(
                    company,
                    i18n,
                    show_run_now=show_run_now,
                    show_show_now=(count > 0),
                    show_autorespond=True,
                    show_sync_negotiations=show_sync,
                ),
            )


# ── Run now ─────────────────────────────────────────────────────────


@router.callback_query(AutoparseCallback.filter(F.action == "run_now"))
async def run_now(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    session: AsyncSession,
    i18n: I18nContext,
    user: User,
) -> None:
    from src.core.celery_async import run_celery_task
    from src.worker.tasks.autoparse import run_autoparse_company

    company = await ap_service.get_autoparse_detail(session, callback_data.company_id)
    if not company:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return

    if not await _should_show_run_now(session, company, user):
        count = await ap_service.get_vacancy_count(session, company.id)
        ar_task_on = await autorespond_globally_enabled(session)
        show_sync = await _user_has_hh_browser_session(session, user.id)
        text = ap_service.format_company_detail(
            company,
            count,
            i18n,
            autorespond_global=True,
            autorespond_task_enabled=ar_task_on,
        )
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                text,
                reply_markup=autoparse_detail_keyboard(
                    company,
                    i18n,
                    show_run_now=False,
                    show_show_now=(count > 0),
                    show_autorespond=True,
                    show_sync_negotiations=show_sync,
                ),
            )
        await callback.answer(i18n.get("autoparse-run-already-running"), show_alert=True)
        return

    company = await ap_service.mark_parsing_started(session, company.id)
    if company is None:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return
    await run_celery_task(run_autoparse_company, company.id, notify_user_id=user.id)
    await callback.answer(i18n.get("autoparse-run-started"), show_alert=True)

    count = await ap_service.get_vacancy_count(session, company.id)
    ar_task_on = await autorespond_globally_enabled(session)
    show_sync = await _user_has_hh_browser_session(session, user.id)
    text = ap_service.format_company_detail(
        company,
        count,
        i18n,
        autorespond_global=True,
        autorespond_task_enabled=ar_task_on,
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=autoparse_detail_keyboard(
                company,
                i18n,
                show_run_now=False,
                show_show_now=(count > 0),
                show_autorespond=True,
                show_sync_negotiations=show_sync,
            ),
        )


# ── Show new vacancies now ───────────────────────────────────────────


@router.callback_query(AutoparseCallback.filter(F.action == "show_now"))
async def show_new_vacancies_now(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    i18n: I18nContext,
) -> None:
    from src.core.celery_async import run_celery_task, run_sync_in_thread
    from src.core.redis import create_async_redis
    from src.worker.app import celery_app
    from src.worker.tasks.autoparse import _DELIVER_TASK_PREFIX, deliver_autoparse_results

    task_key = f"{_DELIVER_TASK_PREFIX}{callback_data.company_id}:{user.id}"
    redis = create_async_redis()
    try:
        scheduled_id = await redis.get(task_key)
        if scheduled_id:
            await run_sync_in_thread(
                celery_app.control.revoke,
                scheduled_id,
                terminate=False,
            )
            await redis.delete(task_key)
    finally:
        await redis.aclose()

    await run_celery_task(
        deliver_autoparse_results,
        callback_data.company_id,
        user.id,
        True,
    )
    await callback.answer(i18n.get("autoparse-delivering-now"), show_alert=True)


# ── Delete ──────────────────────────────────────────────────────────


@router.callback_query(AutoparseCallback.filter(F.action == "delete"))
async def delete_prompt(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    i18n: I18nContext,
) -> None:
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("autoparse-confirm-delete"),
            reply_markup=confirm_delete_keyboard(callback_data.company_id, i18n),
        )
    await callback.answer()


@router.callback_query(AutoparseCallback.filter(F.action == "confirm_delete"))
async def delete_confirmed(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    await ap_service.soft_delete_autoparse_company(session, callback_data.company_id, user.id)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("autoparse-deleted"),
            reply_markup=autoparse_hub_keyboard(i18n),
        )
    await callback.answer()


# ── Download ────────────────────────────────────────────────────────


@router.callback_query(AutoparseCallback.filter(F.action == "download"))
async def download_menu(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    i18n: I18nContext,
) -> None:
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("autoparse-download-title"),
            reply_markup=download_format_keyboard(callback_data.company_id, i18n),
        )
    await callback.answer()


@router.callback_query(AutoparseDownloadCallback.filter())
async def download_file(
    callback: CallbackQuery,
    callback_data: AutoparseDownloadCallback,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    vacancies = await ap_service.get_all_vacancies(session, callback_data.company_id)
    if not vacancies:
        await callback.answer(i18n.get("autoparse-empty-list"), show_alert=True)
        return

    fmt = callback_data.format
    if fmt == "links_txt":
        content = ap_service.generate_links_txt(vacancies)
        filename = f"autoparse_{callback_data.company_id}_links.txt"
    elif fmt == "summary_txt":
        content = ap_service.generate_summary_txt(vacancies)
        filename = f"autoparse_{callback_data.company_id}_summary.txt"
    else:
        content = ap_service.generate_full_md(vacancies)
        filename = f"autoparse_{callback_data.company_id}_full.md"

    doc = BufferedInputFile(content.encode("utf-8"), filename=filename)
    await callback.message.answer_document(doc)
    await callback.answer()


# ── Settings ────────────────────────────────────────────────────────


@router.callback_query(AutoparseCallback.filter(F.action == "settings"))
async def settings_hub(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    current = await ap_service.get_user_autoparse_settings(session, user.id)
    experiences = await parsing_service.get_active_work_experiences(session, user.id)

    if experiences:
        exp_lines = [f"  \u2022 <b>{e.company_name}</b> \u2014 {e.stack}" for e in experiences]
        exp_display = "\n" + "\n".join(exp_lines)
    else:
        exp_display = " —"

    custom_stack = current.get("tech_stack", [])
    if custom_stack:
        stack_display = ", ".join(custom_stack)
    elif experiences:
        derived = ap_service.derive_tech_stack_from_experiences(experiences)
        stack_display = f"{', '.join(derived)} ({i18n.get('autoparse-settings-stack-auto')})"
    else:
        stack_display = "—"

    min_compat = current.get("min_compatibility_percent", 50)
    cover_style = current.get("cover_letter_style", ap_service.DEFAULT_COVER_LETTER_STYLE)
    user_name = current.get("user_name", "").strip()
    if not user_name:
        user_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "—"
    about_me = (current.get("about_me") or "").strip()
    about_me_display = (about_me[:60] + "…") if len(about_me) > 60 else (about_me or "—")
    lines = [
        f"<b>{i18n.get('autoparse-settings-title')}</b>\n",
        f"{i18n.get('autoparse-settings-work-exp')}:{exp_display}\n",
        f"{i18n.get('autoparse-settings-tech-stack')}: {stack_display}\n",
        f"{i18n.get('autoparse-settings-send-time')}: {current.get('send_time', '12:00')}\n",
        f"{i18n.get('autoparse-settings-min-compat')}: {min_compat}%\n",
        f"{i18n.get('autoparse-settings-user-name')}: {user_name}\n",
        f"{i18n.get('autoparse-settings-about-me')}: {about_me_display}\n",
    ]
    if user.is_admin:
        tc = current.get("target_count")
        tc_display = str(tc) if tc is not None else "—"
        lines.append(f"{i18n.get('autoparse-settings-target-count')}: {tc_display}\n")
    lines.append(f"{i18n.get('autoparse-settings-cover-letter-style')}: {cover_style}")
    text = "".join(lines)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text, reply_markup=autoparse_settings_keyboard(i18n, is_admin=user.is_admin)
        )
    await callback.answer()


@router.callback_query(AutoparseSettingsCallback.filter(F.action == "work_exp"))
async def settings_work_exp(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await state.clear()
    from src.bot.modules.work_experience.handlers import show_work_experience

    await show_work_experience(callback.message, user, "autoparse_settings", session, i18n)
    await callback.answer()


@router.callback_query(AutoparseSettingsCallback.filter(F.action == "send_time"))
async def settings_send_time(callback: CallbackQuery, state: FSMContext, i18n: I18nContext) -> None:
    await state.set_state(AutoparseSettingsForm.send_time)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("autoparse-settings-send-time")
            + "\n\n"
            + i18n.get("autoparse-enter-send-time"),
            reply_markup=cancel_keyboard(i18n),
        )
    await callback.answer()


@router.message(AutoparseSettingsForm.send_time)
async def receive_send_time(
    message: Message, state: FSMContext, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    time_str = message.text.strip()
    if ":" not in time_str:
        await message.answer(i18n.get("autoparse-enter-send-time"))
        return
    await ap_service.update_user_autoparse_settings(session, user.id, send_time=time_str)
    await state.clear()
    await message.answer(
        i18n.get("autoparse-settings-saved"),
        reply_markup=autoparse_hub_keyboard(i18n),
    )


@router.callback_query(AutoparseSettingsCallback.filter(F.action == "tech_stack"))
async def settings_tech_stack(
    callback: CallbackQuery, state: FSMContext, i18n: I18nContext
) -> None:
    await state.set_state(AutoparseSettingsForm.tech_stack)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("autoparse-settings-tech-stack")
            + "\n\n"
            + i18n.get("autoparse-enter-tech-stack"),
            reply_markup=cancel_keyboard(i18n),
        )
    await callback.answer()


@router.message(AutoparseSettingsForm.tech_stack)
async def receive_tech_stack(
    message: Message, state: FSMContext, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    stack = [s.strip() for s in message.text.split(",") if s.strip()]
    await ap_service.update_user_autoparse_settings(session, user.id, tech_stack=stack)
    await state.clear()
    await message.answer(
        i18n.get("autoparse-settings-saved"),
        reply_markup=autoparse_hub_keyboard(i18n),
    )


@router.callback_query(AutoparseSettingsCallback.filter(F.action == "min_compat"))
async def settings_min_compat(
    callback: CallbackQuery, state: FSMContext, i18n: I18nContext
) -> None:
    await state.set_state(AutoparseSettingsForm.min_compat_percent)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("autoparse-settings-min-compat")
            + "\n\n"
            + i18n.get("autoparse-enter-min-compat"),
            reply_markup=cancel_keyboard(i18n),
        )
    await callback.answer()


@router.message(AutoparseSettingsForm.min_compat_percent)
async def receive_min_compat_percent(
    message: Message, state: FSMContext, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    raw = message.text.strip()
    compat_min, compat_max = get_min_compat_range(user)
    if not raw.isdigit() or not (compat_min <= int(raw) <= compat_max):
        await message.answer(i18n.get("autoparse-min-compat-invalid"))
        return
    await ap_service.update_user_autoparse_settings(
        session, user.id, min_compatibility_percent=int(raw)
    )
    await state.clear()
    await message.answer(
        i18n.get("autoparse-settings-saved"),
        reply_markup=autoparse_hub_keyboard(i18n),
    )


@router.callback_query(AutoparseSettingsCallback.filter(F.action == "user_name"))
async def settings_user_name(callback: CallbackQuery, state: FSMContext, i18n: I18nContext) -> None:
    await state.set_state(AutoparseSettingsForm.user_name)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("autoparse-settings-user-name")
            + "\n\n"
            + i18n.get("autoparse-enter-user-name"),
            reply_markup=cancel_keyboard(i18n),
        )
    await callback.answer()


@router.message(AutoparseSettingsForm.user_name)
async def receive_user_name(
    message: Message, state: FSMContext, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    name = message.text.strip()
    await ap_service.update_user_autoparse_settings(session, user.id, user_name=name)
    await state.clear()
    await message.answer(
        i18n.get("autoparse-settings-saved"),
        reply_markup=autoparse_hub_keyboard(i18n),
    )


@router.callback_query(AutoparseSettingsCallback.filter(F.action == "about_me"))
async def settings_about_me(callback: CallbackQuery, state: FSMContext, i18n: I18nContext) -> None:
    await state.set_state(AutoparseSettingsForm.about_me)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("autoparse-settings-about-me")
            + "\n\n"
            + i18n.get("autoparse-enter-about-me"),
            reply_markup=cancel_keyboard(i18n),
        )
    await callback.answer()


@router.message(AutoparseSettingsForm.about_me)
async def receive_about_me(
    message: Message, state: FSMContext, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    about_me = message.text.strip() if message.text else ""
    await ap_service.update_user_autoparse_settings(session, user.id, about_me=about_me)
    await state.clear()
    await message.answer(
        i18n.get("autoparse-settings-saved"),
        reply_markup=autoparse_hub_keyboard(i18n),
    )


@router.callback_query(AutoparseSettingsCallback.filter(F.action == "target_count"))
async def settings_target_count(
    callback: CallbackQuery,
    user: User,
    i18n: I18nContext,
) -> None:
    if not user.is_admin:
        await callback.answer()
        return
    text = (
        f"{i18n.get('autoparse-settings-target-count')}\n\n"
        f"{i18n.get('autoparse-settings-target-count-choose')}"
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=target_count_select_keyboard(i18n),
        )
    await callback.answer()


@router.callback_query(
    AutoparseSettingsCallback.filter(
        F.action.in_(
            {"target_count_10", "target_count_30", "target_count_50", "target_count_5000"}
        )
    )
)
async def settings_target_count_select(
    callback: CallbackQuery,
    callback_data: AutoparseSettingsCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    if not user.is_admin:
        await callback.answer()
        return
    mapping = {
        "target_count_10": 10,
        "target_count_30": 30,
        "target_count_50": 50,
        "target_count_5000": 5000,
    }
    val = mapping.get(callback_data.action)
    if val is None:
        await callback.answer()
        return
    await ap_service.update_user_autoparse_settings(session, user.id, target_count=val)
    current = await ap_service.get_user_autoparse_settings(session, user.id)
    experiences = await parsing_service.get_active_work_experiences(session, user.id)
    if experiences:
        exp_lines = [f"  • <b>{e.company_name}</b> — {e.stack}" for e in experiences]
        exp_display = "\n" + "\n".join(exp_lines)
    else:
        exp_display = " —"
    custom_stack = current.get("tech_stack", [])
    if custom_stack:
        stack_display = ", ".join(custom_stack)
    elif experiences:
        derived = ap_service.derive_tech_stack_from_experiences(experiences)
        stack_display = f"{', '.join(derived)} ({i18n.get('autoparse-settings-stack-auto')})"
    else:
        stack_display = "—"
    min_compat = current.get("min_compatibility_percent", 50)
    cover_style = current.get("cover_letter_style", ap_service.DEFAULT_COVER_LETTER_STYLE)
    user_name = current.get("user_name", "").strip()
    if not user_name:
        user_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "—"
    about_me = (current.get("about_me") or "").strip()
    about_me_display = (about_me[:60] + "…") if len(about_me) > 60 else (about_me or "—")
    lines = [
        f"<b>{i18n.get('autoparse-settings-title')}</b>\n",
        f"{i18n.get('autoparse-settings-work-exp')}:{exp_display}\n",
        f"{i18n.get('autoparse-settings-tech-stack')}: {stack_display}\n",
        f"{i18n.get('autoparse-settings-send-time')}: {current.get('send_time', '12:00')}\n",
        f"{i18n.get('autoparse-settings-min-compat')}: {min_compat}%\n",
        f"{i18n.get('autoparse-settings-user-name')}: {user_name}\n",
        f"{i18n.get('autoparse-settings-about-me')}: {about_me_display}\n",
        f"{i18n.get('autoparse-settings-target-count')}: {current.get('target_count') or '—'}\n",
        f"{i18n.get('autoparse-settings-cover-letter-style')}: {cover_style}",
    ]
    text = "".join(lines)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=autoparse_settings_keyboard(i18n, is_admin=user.is_admin),
        )
    await callback.answer(i18n.get("autoparse-settings-saved"), show_alert=True)


@router.callback_query(AutoparseSettingsCallback.filter(F.action == "cover_letter_style"))
async def settings_cover_letter_style(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    current = await ap_service.get_user_autoparse_settings(session, user.id)
    cover_style = current.get("cover_letter_style", ap_service.DEFAULT_COVER_LETTER_STYLE)
    text = (
        f"{i18n.get('autoparse-cover-letter-style-current', style=cover_style)}\n\n"
        f"{i18n.get('autoparse-cover-letter-style-choose')}"
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=cover_letter_style_keyboard(i18n),
        )
    await callback.answer()


@router.callback_query(
    AutoparseSettingsCallback.filter(
        F.action.in_(
            {
                "cover_letter_style_professional",
                "cover_letter_style_friendly",
                "cover_letter_style_concise",
                "cover_letter_style_detailed",
            }
        )
    )
)
async def settings_cover_letter_style_select(
    callback: CallbackQuery,
    callback_data: AutoparseSettingsCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    prefix = "cover_letter_style_"
    style = (
        callback_data.action[len(prefix) :]
        if callback_data.action.startswith(prefix)
        else "professional"
    )
    await ap_service.update_user_autoparse_settings(
        session, user.id, cover_letter_style=style
    )
    current = await ap_service.get_user_autoparse_settings(session, user.id)
    experiences = await parsing_service.get_active_work_experiences(session, user.id)
    if experiences:
        exp_lines = [f"  \u2022 <b>{e.company_name}</b> \u2014 {e.stack}" for e in experiences]
        exp_display = "\n" + "\n".join(exp_lines)
    else:
        exp_display = " —"
    custom_stack = current.get("tech_stack", [])
    if custom_stack:
        stack_display = ", ".join(custom_stack)
    elif experiences:
        derived = ap_service.derive_tech_stack_from_experiences(experiences)
        stack_display = f"{', '.join(derived)} ({i18n.get('autoparse-settings-stack-auto')})"
    else:
        stack_display = "—"
    min_compat = current.get("min_compatibility_percent", 50)
    cover_style = current.get("cover_letter_style", ap_service.DEFAULT_COVER_LETTER_STYLE)
    user_name = current.get("user_name", "").strip()
    if not user_name:
        user_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "—"
    about_me = (current.get("about_me") or "").strip()
    about_me_display = (about_me[:60] + "…") if len(about_me) > 60 else (about_me or "—")
    lines = [
        f"<b>{i18n.get('autoparse-settings-title')}</b>\n\n",
        f"{i18n.get('autoparse-settings-work-exp')}:{exp_display}\n\n",
        f"{i18n.get('autoparse-settings-tech-stack')}: {stack_display}\n",
        f"{i18n.get('autoparse-settings-send-time')}: {current.get('send_time', '12:00')}\n",
        f"{i18n.get('autoparse-settings-min-compat')}: {min_compat}%\n",
        f"{i18n.get('autoparse-settings-user-name')}: {user_name}\n",
        f"{i18n.get('autoparse-settings-about-me')}: {about_me_display}\n",
    ]
    if user.is_admin:
        tc = current.get("target_count")
        tc_display = str(tc) if tc is not None else "—"
        lines.append(f"{i18n.get('autoparse-settings-target-count')}: {tc_display}\n")
    lines.append(f"{i18n.get('autoparse-settings-cover-letter-style')}: {cover_style}")
    text = "".join(lines)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=autoparse_settings_keyboard(i18n, is_admin=user.is_admin),
        )
    await callback.answer()


@router.callback_query(
    AutoparseSettingsCallback.filter(F.action == "cover_letter_style_custom")
)
async def settings_cover_letter_style_custom(
    callback: CallbackQuery, state: FSMContext, i18n: I18nContext
) -> None:
    await state.set_state(AutoparseSettingsForm.cover_letter_style_custom)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("autoparse-enter-cover-letter-style"),
            reply_markup=cancel_keyboard(i18n),
        )
    await callback.answer()


@router.message(AutoparseSettingsForm.cover_letter_style_custom)
async def receive_cover_letter_style_custom(
    message: Message, state: FSMContext, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    custom_style = message.text.strip() if message.text else ""
    if not custom_style:
        await message.answer(i18n.get("autoparse-enter-cover-letter-style"))
        return
    await ap_service.update_user_autoparse_settings(
        session, user.id, cover_letter_style=custom_style
    )
    await state.clear()
    await message.answer(
        i18n.get("autoparse-settings-saved"),
        reply_markup=autoparse_hub_keyboard(i18n),
    )
