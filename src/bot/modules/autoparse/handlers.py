"""Handlers for the Autoparse feature."""

import contextlib
from urllib.parse import parse_qs, urlparse

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.modules.autoparse import services as ap_service
from src.bot.modules.autoparse.autorespond_handlers import (
    autorespond_globally_enabled,
)
from src.bot.modules.autoparse.autorespond_handlers import (
    router as autorespond_router,
)
from src.bot.modules.autoparse.callbacks import (
    AutoparseCallback,
    AutoparseDownloadCallback,
    AutoparseSettingsCallback,
)
from src.bot.modules.autoparse.feed_handlers import router as feed_router
from src.bot.modules.autoparse.keyboards import (
    autoparse_detail_keyboard,
    autoparse_hub_keyboard,
    autoparse_list_keyboard,
    autoparse_settings_keyboard,
    cancel_keyboard,
    confirm_delete_keyboard,
    confirm_rebuild_company_keyboard,
    confirm_reset_disliked_keyboard,
    confirm_reset_likes_keyboard,
    cover_letter_style_keyboard,
    download_format_keyboard,
    liked_disliked_list_keyboard,
    parse_hh_account_keyboard,
    parse_login_required_keyboard,
    parse_mode_keyboard,
    target_count_select_keyboard,
    template_list_keyboard,
)
from src.bot.modules.autoparse.states import AutoparseEditForm, AutoparseForm, AutoparseSettingsForm
from src.bot.modules.parsing import services as parsing_service
from src.config import settings
from src.bot.utils.limits import get_min_compat_range
from src.core.i18n import I18nContext
from src.models.autoparse import AutoparseCompany
from src.models.user import User
from src.repositories.autoparse import AutoparsedVacancyRepository
from src.repositories.hh_linked_account import HhLinkedAccountRepository
from src.repositories.parsing import ParsingCompanyRepository
from src.repositories.vacancy_feed import VacancyFeedSessionRepository
from src.services.autoparse_delivery import revoke_scheduled_delivery_async
from src.services.autoparse_feed_cards import build_feed_stats_card, create_feed_session
from src.services.autoparse_use_cases import build_company_detail_view

router = Router(name="autoparse")
router.include_router(feed_router)
router.include_router(autorespond_router)

_PER_PAGE = 5
_VACANCIES_PER_PAGE = 15
_EDIT_PROMPT_MAX_LEN = 100


def _truncate_for_edit_prompt(text: str, max_len: int = _EDIT_PROMPT_MAX_LEN) -> str:
    t = text.strip()
    if len(t) <= max_len:
        return t
    return f"{t[:max_len]}…"


def _search_url_resume_id(url: str) -> str | None:
    try:
        values = parse_qs(urlparse(url).query).get("resume") or []
    except ValueError:
        return None
    for value in values:
        resume_id = value.strip()
        if resume_id:
            return resume_id
    return None


def _login_assist_available() -> bool:
    return bool(
        settings.hh_login_assist_enabled
        and settings.hh_ui_apply_enabled
        and settings.hh_token_encryption_key
    )


def _parse_mode_label(i18n: I18nContext, mode: str) -> str:
    return i18n.get(
        "autoparse-parse-mode-web-label" if mode == "web" else "autoparse-parse-mode-api-label"
    )


async def _has_tech_stack(session: AsyncSession, user_id: int) -> bool:
    """Return True if the user already has a tech stack (manual or from work experience)."""
    settings = await ap_service.get_user_autoparse_settings(session, user_id)
    if settings.get("tech_stack"):
        return True
    experiences = await parsing_service.get_active_work_experiences(session, user_id)
    return bool(experiences)


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


async def _prompt_parse_mode_step(
    target: CallbackQuery | Message,
    state: FSMContext,
    i18n: I18nContext,
    *,
    company_id: int = 0,
    flow: str = "create",
) -> None:
    await state.update_data(
        parse_pending_flow=flow,
        parse_pending_company_id=company_id,
        parse_pending_parse_mode=None,
        parse_pending_hh_linked_account_id=None,
        parse_pending_selected_hh_account_id=None,
    )
    await state.set_state(
        AutoparseForm.parse_mode if flow == "create" else AutoparseEditForm.edit_parse_mode
    )
    if isinstance(target, CallbackQuery):
        with contextlib.suppress(TelegramBadRequest):
            await target.message.edit_text(
                i18n.get("autoparse-parse-mode-prompt"),
                reply_markup=parse_mode_keyboard(
                    i18n,
                    company_id=company_id,
                    back_action="hub" if flow == "create" else "detail",
                ),
            )
        await target.answer()
        return
    await target.answer(
        i18n.get("autoparse-parse-mode-prompt"),
        reply_markup=parse_mode_keyboard(
            i18n,
            company_id=company_id,
            back_action="hub" if flow == "create" else "detail",
        ),
    )


async def _finalize_pending_parse_setup(
    target: CallbackQuery | Message,
    *,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    flow = data.get("parse_pending_flow") or "create"
    parse_mode = data.get("parse_pending_parse_mode") or data.get("parse_mode") or "api"
    parse_hh_linked_account_id = data.get("parse_pending_hh_linked_account_id")

    if flow == "create":
        company = await ap_service.create_autoparse_company(
            session,
            user.id,
            data["vacancy_title"],
            data["search_url"],
            data.get("keyword_filter", ""),
            data.get("skills", ""),
            keyword_check_enabled=True,
            parse_mode=parse_mode,
            parse_hh_linked_account_id=parse_hh_linked_account_id,
        )
        await state.clear()
        if isinstance(target, CallbackQuery):
            with contextlib.suppress(TelegramBadRequest):
                await target.message.edit_text(
                    i18n.get("autoparse-created-success", id=str(company.id)),
                    reply_markup=autoparse_hub_keyboard(i18n),
                )
            await target.answer()
        else:
            await target.answer(
                i18n.get("autoparse-created-success", id=str(company.id)),
                reply_markup=autoparse_hub_keyboard(i18n),
            )
        return

    company_id = int(data.get("parse_pending_company_id") or 0)
    detail_message_id = int(data.get("parse_pending_detail_message_id") or 0)
    if not company_id:
        await state.clear()
        if isinstance(target, CallbackQuery):
            await target.answer(i18n.get("autoparse-not-found"), show_alert=True)
        else:
            await target.answer(i18n.get("autoparse-not-found"))
        return

    from src.repositories.autoparse import AutoparseCompanyRepository

    repo = AutoparseCompanyRepository(session)
    company = await repo.get_by_id_for_user(company_id, user.id)
    if not company:
        await state.clear()
        if isinstance(target, CallbackQuery):
            await target.answer(i18n.get("autoparse-not-found"), show_alert=True)
        else:
            await target.answer(i18n.get("autoparse-not-found"))
        return

    updates: dict = {}
    if flow == "edit_parse_mode":
        updates["parse_mode"] = parse_mode
        updates["parse_hh_linked_account_id"] = parse_hh_linked_account_id
    elif flow == "edit_search_url":
        updates["search_url"] = data.get("parse_pending_search_url") or company.search_url
        if company.parse_mode == "web":
            updates["parse_hh_linked_account_id"] = parse_hh_linked_account_id

    await repo.update(company, **updates)
    await session.commit()
    await state.clear()

    with contextlib.suppress(TelegramBadRequest):
        target_bot = target.message.bot if isinstance(target, CallbackQuery) else target.bot
        target_chat_id = target.message.chat.id if isinstance(target, CallbackQuery) else target.chat.id
        if detail_message_id:
            await _edit_company_detail_message_by_id(
                bot=target_bot,
                chat_id=target_chat_id,
                message_id=detail_message_id,
                user=user,
                session=session,
                i18n=i18n,
                company=company,
            )

    saved_key = (
        "autoparse-edit-parse-mode-saved"
        if flow == "edit_parse_mode"
        else "autoparse-edit-search-url-saved"
    )
    if isinstance(target, CallbackQuery):
        await target.answer(i18n.get(saved_key), show_alert=True)
    else:
        await target.answer(i18n.get(saved_key))


async def _continue_web_parse_setup(
    target: CallbackQuery | Message,
    *,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    flow = data.get("parse_pending_flow") or "create"
    company_id = int(data.get("parse_pending_company_id") or 0)
    url = (
        data.get("parse_pending_search_url")
        or data.get("search_url")
        or ""
    )
    if not _search_url_resume_id(str(url)):
        await state.update_data(parse_pending_hh_linked_account_id=None)
        await _finalize_pending_parse_setup(
            target,
            state=state,
            user=user,
            session=session,
            i18n=i18n,
        )
        return

    hh_repo = HhLinkedAccountRepository(session)
    accounts = await hh_repo.list_active_for_user(user.id)
    ready_accounts = [acc for acc in accounts if acc.browser_storage_enc]
    preferred_account_id = data.get("parse_pending_hh_linked_account_id")

    if preferred_account_id:
        for acc in ready_accounts:
            if acc.id == preferred_account_id:
                await state.update_data(
                    parse_pending_hh_linked_account_id=acc.id,
                    parse_pending_selected_hh_account_id=acc.id,
                )
                await _finalize_pending_parse_setup(
                    target,
                    state=state,
                    user=user,
                    session=session,
                    i18n=i18n,
                )
                return

    if len(ready_accounts) == 1:
        await state.update_data(parse_pending_hh_linked_account_id=ready_accounts[0].id)
        await _finalize_pending_parse_setup(
            target,
            state=state,
            user=user,
            session=session,
            i18n=i18n,
        )
        return

    prompt_back_action = "hub" if flow == "create" else "detail"
    prompt_state = AutoparseForm.parse_hh_account if flow == "create" else AutoparseEditForm.edit_parse_mode
    await state.set_state(prompt_state)

    if len(accounts) > 1 or len(ready_accounts) > 1:
        if isinstance(target, CallbackQuery):
            with contextlib.suppress(TelegramBadRequest):
                await target.message.edit_text(
                    i18n.get("autoparse-parse-account-pick"),
                    reply_markup=parse_hh_account_keyboard(
                        accounts,
                        i18n,
                        company_id=company_id,
                        back_action=prompt_back_action,
                    ),
                    parse_mode="HTML",
                )
            await target.answer()
            return
        await target.answer(
            i18n.get("autoparse-parse-account-pick"),
            reply_markup=parse_hh_account_keyboard(
                accounts,
                i18n,
                company_id=company_id,
                back_action=prompt_back_action,
            ),
            parse_mode="HTML",
        )
        return

    selected_account_id = accounts[0].id if accounts else None
    await state.update_data(parse_pending_selected_hh_account_id=selected_account_id)
    if accounts:
        label = accounts[0].label or accounts[0].hh_user_id
        text = i18n.get("autoparse-parse-login-for-account", label=label[:80])
    else:
        text = i18n.get("autoparse-parse-login-required")

    if isinstance(target, CallbackQuery):
        with contextlib.suppress(TelegramBadRequest):
            await target.message.edit_text(
                text,
                reply_markup=parse_login_required_keyboard(
                    i18n,
                    company_id=company_id,
                    back_action=prompt_back_action,
                ),
                parse_mode="HTML",
            )
        await target.answer()
        return
    await target.answer(
        text,
        reply_markup=parse_login_required_keyboard(
            i18n,
            company_id=company_id,
            back_action=prompt_back_action,
        ),
        parse_mode="HTML",
    )


async def _render_autoparse_list(
    message: Message,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
    page: int,
) -> None:
    companies, total = await ap_service.get_user_autoparse_companies(
        session, user.id, page, _PER_PAGE
    )
    if not companies and page == 0:
        with contextlib.suppress(TelegramBadRequest):
            await message.edit_text(
                i18n.get("autoparse-empty-list"),
                reply_markup=autoparse_hub_keyboard(i18n),
            )
        return

    has_more = (page + 1) * _PER_PAGE < total
    with contextlib.suppress(TelegramBadRequest):
        await message.edit_text(
            i18n.get("autoparse-list-title"),
            reply_markup=autoparse_list_keyboard(companies, page, has_more, i18n),
        )


async def _render_company_detail_message(
    message: Message,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
    company: AutoparseCompany,
) -> None:
    ar_task_on = await autorespond_globally_enabled(session)
    view = await build_company_detail_view(
        session,
        company=company,
        user=user,
        i18n=i18n,
        autorespond_global=True,
        autorespond_task_enabled=ar_task_on,
    )
    with contextlib.suppress(TelegramBadRequest):
        await message.edit_text(
            view.text,
            reply_markup=autoparse_detail_keyboard(
                company,
                i18n,
                show_run_now=view.show_run_now,
                show_show_now=view.show_show_now,
                show_autorespond=True,
                show_sync_negotiations=view.show_sync_negotiations,
            ),
            parse_mode="HTML",
        )


async def _edit_company_detail_message_by_id(
    *,
    bot,
    chat_id: int,
    message_id: int,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
    company: AutoparseCompany,
) -> None:
    ar_task_on = await autorespond_globally_enabled(session)
    view = await build_company_detail_view(
        session,
        company=company,
        user=user,
        i18n=i18n,
        autorespond_global=True,
        autorespond_task_enabled=ar_task_on,
    )
    await bot.edit_message_text(
        view.text,
        chat_id=chat_id,
        message_id=message_id,
        reply_markup=autoparse_detail_keyboard(
            company,
            i18n,
            show_run_now=view.show_run_now,
            show_show_now=view.show_show_now,
            show_autorespond=True,
            show_sync_negotiations=view.show_sync_negotiations,
        ),
        parse_mode="HTML",
    )


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
    company = await repo.get_by_id_for_user(callback_data.company_id, user.id)
    if not company:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return

    await state.update_data(
        vacancy_title=company.vacancy_title,
        search_url=company.search_url,
        keyword_filter=company.keyword_filter,
        skills="",
        parse_mode="api",
        parse_hh_linked_account_id=None,
    )

    if await _has_tech_stack(session, user.id):
        await _prompt_parse_mode_step(callback, state, i18n)
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
    await state.update_data(
        keyword_filter=message.text.strip(),
        skills="",
        parse_mode="api",
        parse_hh_linked_account_id=None,
    )

    if await _has_tech_stack(session, user.id):
        await _prompt_parse_mode_step(message, state, i18n)
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
    await state.update_data(
        skills=message.text.strip(),
        parse_mode="api",
        parse_hh_linked_account_id=None,
    )
    await _prompt_parse_mode_step(message, state, i18n)


@router.callback_query(AutoparseCallback.filter(F.action == "parse_mode_api"))
async def parse_mode_api_selected(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    flow = data.get("parse_pending_flow") or "create"
    await state.update_data(
        parse_pending_parse_mode="api",
        parse_pending_hh_linked_account_id=None,
        parse_pending_selected_hh_account_id=None,
        parse_mode="api" if flow == "create" else data.get("parse_mode"),
        parse_hh_linked_account_id=None if flow == "create" else data.get("parse_hh_linked_account_id"),
    )
    await _finalize_pending_parse_setup(
        callback,
        state=state,
        user=user,
        session=session,
        i18n=i18n,
    )


@router.callback_query(AutoparseCallback.filter(F.action == "parse_mode_web"))
async def parse_mode_web_selected(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await state.update_data(
        parse_pending_parse_mode="web",
        parse_mode="web",
    )
    await _continue_web_parse_setup(
        callback,
        state=state,
        user=user,
        session=session,
        i18n=i18n,
    )


@router.callback_query(AutoparseCallback.filter(F.action == "parse_pick_hh_account"))
async def parse_pick_hh_account(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    hh_repo = HhLinkedAccountRepository(session)
    acc = await hh_repo.get_by_id(callback_data.aux_id)
    if not acc or acc.user_id != user.id:
        await callback.answer(i18n.get("autorespond-no-hh-account"), show_alert=True)
        return

    if acc.browser_storage_enc:
        await state.update_data(
            parse_pending_hh_linked_account_id=acc.id,
            parse_pending_selected_hh_account_id=acc.id,
        )
        await _finalize_pending_parse_setup(
            callback,
            state=state,
            user=user,
            session=session,
            i18n=i18n,
        )
        return

    flow = (await state.get_data()).get("parse_pending_flow") or "create"
    await state.update_data(parse_pending_selected_hh_account_id=acc.id)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("autoparse-parse-login-for-account", label=(acc.label or acc.hh_user_id)[:80]),
            reply_markup=parse_login_required_keyboard(
                i18n,
                company_id=int((await state.get_data()).get("parse_pending_company_id") or 0),
                back_action="hub" if flow == "create" else "detail",
            ),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(AutoparseCallback.filter(F.action == "parse_login_now"))
async def parse_login_now(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    if not _login_assist_available():
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("autoparse-parse-no-login-assist"),
                reply_markup=parse_login_required_keyboard(i18n),
            )
        await callback.answer()
        return

    from src.core.celery_async import run_celery_task
    from src.worker.tasks.hh_login_assist import hh_login_assist_task

    data = await state.get_data()
    selected_account_id = data.get("parse_pending_selected_hh_account_id")
    flow = data.get("parse_pending_flow") or "create"
    company_id = int(data.get("parse_pending_company_id") or 0)

    await callback.message.answer(
        i18n.get("autoparse-parse-login-followup"),
        reply_markup=parse_login_required_keyboard(
            i18n,
            company_id=company_id,
            back_action="hub" if flow == "create" else "detail",
        ),
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(i18n.get("autoparse-parse-login-started"))
    await callback.answer()
    await run_celery_task(
        hh_login_assist_task,
        user.id,
        callback.message.chat.id,
        callback.message.message_id,
        i18n.locale,
        hh_linked_account_id=selected_account_id,
    )


@router.callback_query(AutoparseCallback.filter(F.action == "parse_continue_after_login"))
async def parse_continue_after_login(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await _continue_web_parse_setup(
        callback,
        state=state,
        user=user,
        session=session,
        i18n=i18n,
    )


# ── List ────────────────────────────────────────────────────────────


@router.callback_query(AutoparseCallback.filter(F.action == "list"))
async def list_companies(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await _render_autoparse_list(callback.message, user, session, i18n, callback_data.page)
    await callback.answer()


@router.callback_query(AutoparseCallback.filter(F.action == "reset_likes_prompt"))
async def reset_likes_prompt(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    company = await ap_service.get_autoparse_detail(session, callback_data.company_id, user.id)
    if not company:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return
    feed_repo = VacancyFeedSessionRepository(session)
    liked_ids = await feed_repo.get_liked_vacancy_ids_for_user_company(user.id, company.id)
    if not liked_ids:
        await callback.answer(i18n.get("autoparse-reset-likes-empty"), show_alert=True)
        return
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("autoparse-confirm-reset-likes"),
            reply_markup=confirm_reset_likes_keyboard(company.id, i18n),
        )
    await callback.answer()


@router.callback_query(AutoparseCallback.filter(F.action == "confirm_reset_likes"))
async def confirm_reset_likes(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    company = await ap_service.get_autoparse_detail(session, callback_data.company_id, user.id)
    if not company:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return
    feed_repo = VacancyFeedSessionRepository(session)
    await feed_repo.clear_liked_ids_for_user_company(user.id, company.id)
    await session.commit()
    await _render_company_detail_message(callback.message, user, session, i18n, company)
    await callback.answer(i18n.get("autoparse-reset-likes-done"))


@router.callback_query(AutoparseCallback.filter(F.action == "reset_disliked_prompt"))
async def reset_disliked_prompt(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    company = await ap_service.get_autoparse_detail(session, callback_data.company_id, user.id)
    if not company:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return
    feed_repo = VacancyFeedSessionRepository(session)
    disliked_ids = await feed_repo.get_disliked_vacancy_ids_for_user_company(
        user.id, company.id
    )
    if not disliked_ids:
        await callback.answer(i18n.get("autoparse-reset-dislikes-empty"), show_alert=True)
        return
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("autoparse-confirm-reset-dislikes"),
            reply_markup=confirm_reset_disliked_keyboard(company.id, i18n),
        )
    await callback.answer()


@router.callback_query(AutoparseCallback.filter(F.action == "confirm_reset_disliked"))
async def confirm_reset_disliked(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    company = await ap_service.get_autoparse_detail(session, callback_data.company_id, user.id)
    if not company:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return
    feed_repo = VacancyFeedSessionRepository(session)
    await feed_repo.clear_disliked_ids_for_user_company(user.id, company.id)
    await session.commit()
    await _render_company_detail_message(callback.message, user, session, i18n, company)
    await callback.answer(i18n.get("autoparse-reset-dislikes-done"))


@router.callback_query(AutoparseCallback.filter(F.action == "rebuild_pool_prompt"))
async def rebuild_pool_prompt(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    company = await ap_service.get_autoparse_detail(session, callback_data.company_id, user.id)
    if not company:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("autoparse-confirm-rebuild-pool"),
            reply_markup=confirm_rebuild_company_keyboard(company.id, i18n),
        )
    await callback.answer()


@router.callback_query(AutoparseCallback.filter(F.action == "confirm_rebuild_pool"))
async def confirm_rebuild_pool(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    company = await ap_service.get_autoparse_detail(session, callback_data.company_id, user.id)
    if not company:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return

    company = await ap_service.reset_company_vacancy_pool(session, company.id, user.id)
    if company is None:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return

    await _render_company_detail_message(callback.message, user, session, i18n, company)
    await callback.answer(i18n.get("autoparse-rebuild-pool-started"), show_alert=True)


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
    page = callback_data.page
    start = page * _VACANCIES_PER_PAGE
    page_ids, total_liked = await feed_repo.get_liked_vacancy_page_for_user(
        user.id,
        offset=start,
        limit=_VACANCIES_PER_PAGE,
    )
    if not page_ids:
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("autoparse-liked-empty"),
                reply_markup=liked_disliked_list_keyboard("show_liked", 0, False, i18n),
            )
        return

    has_more = start + _VACANCIES_PER_PAGE < total_liked

    vacancies = await vacancy_repo.get_by_ids_simple(page_ids)
    order = {vid: i for i, vid in enumerate(page_ids)}
    vacancies_sorted = sorted(vacancies, key=lambda v: order.get(v.id, 999))

    lines = [f"<b>{i18n.get('autoparse-btn-show-liked')}</b> ({total_liked})\n"]
    for i, v in enumerate(vacancies_sorted, start=start + 1):
        safe_title = v.title.replace("<", "&lt;").replace(">", "&gt;")
        lines.append(f"{i}. <a href='{v.url}'>{safe_title}</a>")
    text = "\n".join(lines)

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=liked_disliked_list_keyboard("show_liked", page, has_more, i18n),
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
    page = callback_data.page
    start = page * _VACANCIES_PER_PAGE
    page_ids, total_disliked = await feed_repo.get_disliked_vacancy_page_for_user(
        user.id,
        offset=start,
        limit=_VACANCIES_PER_PAGE,
    )
    if not page_ids:
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("autoparse-disliked-empty"),
                reply_markup=liked_disliked_list_keyboard("show_disliked", 0, False, i18n),
            )
        return

    has_more = start + _VACANCIES_PER_PAGE < total_disliked

    vacancies = await vacancy_repo.get_by_ids_simple(page_ids)
    order = {vid: i for i, vid in enumerate(page_ids)}
    vacancies_sorted = sorted(vacancies, key=lambda v: order.get(v.id, 999))

    lines = [f"<b>{i18n.get('autoparse-btn-show-disliked')}</b> ({total_disliked})\n"]
    for i, v in enumerate(vacancies_sorted, start=start + 1):
        safe_title = v.title.replace("<", "&lt;").replace(">", "&gt;")
        lines.append(f"{i}. <a href='{v.url}'>{safe_title}</a>")
    text = "\n".join(lines)

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=liked_disliked_list_keyboard("show_disliked", page, has_more, i18n),
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
    vacancies = await vacancy_repo.get_below_min_compat_for_user(user.id, min_compat, reacted_ids)
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

    from src.services.hh.feed_gating import HhFeedAccountStatus, classify_user_hh_accounts

    hh_status, hh_accounts = await classify_user_hh_accounts(session, user.id)
    hh_linked_id = hh_accounts[0].id if hh_status == HhFeedAccountStatus.SINGLE else None

    feed_session_id = await create_feed_session(
        session,
        user_id=user.id,
        company_id=first_company_id,
        chat_id=user.telegram_id,
        vacancy_ids=[v.id for v in vacancies],
        hh_linked_account_id=hh_linked_id,
    )
    title = i18n.get("autoparse-feed-below-compat-title")
    text, keyboard = build_feed_stats_card(
        vacancy_title=title,
        vacancies=vacancies,
        feed_session_id=feed_session_id,
        locale=i18n.locale,
        linked_accounts=hh_accounts,
        back_action="list",
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
    company = await ap_service.get_autoparse_detail(session, callback_data.company_id, user.id)
    if not company:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return

    await _render_company_detail_message(callback.message, user, session, i18n, company)
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

    company = await ap_service.get_autoparse_detail(session, callback_data.company_id, user.id)
    if not company:
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
    company = await ap_service.get_autoparse_detail(session, callback_data.company_id, user.id)
    if not company:
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
    company = await repo.get_by_id_for_user(company_id, user.id)
    if not company:
        await message.answer(i18n.get("autoparse-not-found"))
        return

    await repo.update(company, keyword_filter=message.text.strip())
    await session.commit()

    with contextlib.suppress(TelegramBadRequest):
        await _edit_company_detail_message_by_id(
            bot=message.bot,
            chat_id=message.chat.id,
            message_id=detail_message_id,
            user=user,
            session=session,
            i18n=i18n,
            company=company,
        )
    await message.answer(i18n.get("autoparse-edit-keywords-saved"))


# ── Edit search URL ─────────────────────────────────────────────────


@router.callback_query(AutoparseCallback.filter(F.action == "edit_parse_mode"))
async def edit_parse_mode_start(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    company = await ap_service.get_autoparse_detail(session, callback_data.company_id, user.id)
    if not company:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return

    await state.update_data(
        parse_pending_flow="edit_parse_mode",
        parse_pending_company_id=company.id,
        parse_pending_detail_message_id=callback.message.message_id,
        parse_pending_search_url=company.search_url,
        parse_pending_parse_mode=company.parse_mode or "api",
        parse_pending_hh_linked_account_id=company.parse_hh_linked_account_id,
        parse_mode=company.parse_mode or "api",
        parse_hh_linked_account_id=company.parse_hh_linked_account_id,
    )
    await _prompt_parse_mode_step(
        callback,
        state,
        i18n,
        company_id=company.id,
        flow="edit_parse_mode",
    )


@router.callback_query(AutoparseCallback.filter(F.action == "edit_search_url"))
async def edit_search_url_start(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    company = await ap_service.get_autoparse_detail(session, callback_data.company_id, user.id)
    if not company:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return

    await state.set_state(AutoparseEditForm.edit_search_url)
    await state.update_data(
        edit_search_url_company_id=company.id,
        edit_search_url_message_id=callback.message.message_id,
    )
    current = _truncate_for_edit_prompt(company.search_url or "")
    await callback.message.answer(
        i18n.get("autoparse-edit-search-url-prompt", current=current),
        reply_markup=cancel_keyboard(i18n),
    )
    await callback.answer()


@router.message(AutoparseEditForm.edit_search_url, F.text)
async def edit_search_url_receive(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    company_id = data.get("edit_search_url_company_id")
    detail_message_id = data.get("edit_search_url_message_id")

    if not company_id:
        await state.clear()
        await message.answer(i18n.get("autoparse-not-found"))
        return

    url = message.text.strip()
    if not url.startswith("http"):
        await message.answer(i18n.get("autoparse-enter-url"))
        return

    from src.repositories.autoparse import AutoparseCompanyRepository

    repo = AutoparseCompanyRepository(session)
    company = await repo.get_by_id_for_user(company_id, user.id)
    if not company:
        await state.clear()
        await message.answer(i18n.get("autoparse-not-found"))
        return

    if company.parse_mode == "web":
        await state.update_data(
            parse_pending_flow="edit_search_url",
            parse_pending_company_id=company.id,
            parse_pending_detail_message_id=detail_message_id,
            parse_pending_search_url=url,
            parse_pending_parse_mode=company.parse_mode,
            parse_pending_hh_linked_account_id=company.parse_hh_linked_account_id,
            parse_mode=company.parse_mode,
            parse_hh_linked_account_id=company.parse_hh_linked_account_id,
        )
        await _continue_web_parse_setup(
            message,
            state=state,
            user=user,
            session=session,
            i18n=i18n,
        )
        return

    await repo.update(company, search_url=url, parse_hh_linked_account_id=None)
    await session.commit()
    await state.clear()

    with contextlib.suppress(TelegramBadRequest):
        await _edit_company_detail_message_by_id(
            bot=message.bot,
            chat_id=message.chat.id,
            message_id=detail_message_id,
            user=user,
            session=session,
            i18n=i18n,
            company=company,
        )
    await message.answer(i18n.get("autoparse-edit-search-url-saved"))


# ── Toggle ──────────────────────────────────────────────────────────


@router.callback_query(AutoparseCallback.filter(F.action == "toggle"))
async def toggle_company(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    company = await ap_service.toggle_autoparse_company(session, callback_data.company_id, user.id)
    if not company:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return
    msg = (
        i18n.get("autoparse-toggle-enabled")
        if company.is_enabled
        else i18n.get("autoparse-toggle-disabled")
    )
    await callback.answer(msg, show_alert=True)
    await _render_company_detail_message(callback.message, user, session, i18n, company)


@router.callback_query(AutoparseCallback.filter(F.action == "toggle_keyword_check"))
async def toggle_keyword_check(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    company = await ap_service.toggle_autoparse_keyword_check(
        session, callback_data.company_id, user.id
    )
    if not company:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return
    msg = (
        i18n.get("autoparse-toggle-keyword-check-enabled")
        if company.keyword_check_enabled
        else i18n.get("autoparse-toggle-keyword-check-disabled")
    )
    await callback.answer(msg, show_alert=True)
    await _render_company_detail_message(callback.message, user, session, i18n, company)


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

    company = await ap_service.get_autoparse_detail(session, callback_data.company_id, user.id)
    if not company:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return

    view = await build_company_detail_view(
        session,
        company=company,
        user=user,
        i18n=i18n,
        autorespond_global=True,
        autorespond_task_enabled=await autorespond_globally_enabled(session),
    )
    if not view.show_run_now:
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                view.text,
                reply_markup=autoparse_detail_keyboard(
                    company,
                    i18n,
                    show_run_now=False,
                    show_show_now=view.show_show_now,
                    show_autorespond=True,
                    show_sync_negotiations=view.show_sync_negotiations,
                ),
                parse_mode="HTML",
            )
        await callback.answer(i18n.get("autoparse-run-already-running"), show_alert=True)
        return

    company = await ap_service.mark_parsing_started(session, company.id, user.id)
    if company is None:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return
    await run_celery_task(run_autoparse_company, company.id, notify_user_id=user.id)
    await callback.answer(i18n.get("autoparse-run-started"), show_alert=True)
    refreshed_view = await build_company_detail_view(
        session,
        company=company,
        user=user,
        i18n=i18n,
        autorespond_global=True,
        autorespond_task_enabled=await autorespond_globally_enabled(session),
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            refreshed_view.text,
            reply_markup=autoparse_detail_keyboard(
                company,
                i18n,
                show_run_now=False,
                show_show_now=refreshed_view.show_show_now,
                show_autorespond=True,
                show_sync_negotiations=refreshed_view.show_sync_negotiations,
            ),
            parse_mode="HTML",
        )


# ── Show new vacancies now ───────────────────────────────────────────


@router.callback_query(AutoparseCallback.filter(F.action == "show_now"))
async def show_new_vacancies_now(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.core.celery_async import run_celery_task
    from src.worker.tasks.autoparse import deliver_autoparse_results

    company = await ap_service.get_autoparse_detail(session, callback_data.company_id, user.id)
    if not company:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return

    await revoke_scheduled_delivery_async(company.id, user.id)

    await run_celery_task(
        deliver_autoparse_results,
        company.id,
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
    deleted = await ap_service.soft_delete_autoparse_company(session, callback_data.company_id, user.id)
    if not deleted:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return
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
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    vacancies = await ap_service.get_all_vacancies(session, callback_data.company_id, user.id)
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
            i18n.get("autoparse-settings-about-me") + "\n\n" + i18n.get("autoparse-enter-about-me"),
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
        F.action.in_({"target_count_10", "target_count_30", "target_count_50", "target_count_5000"})
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
    await ap_service.update_user_autoparse_settings(session, user.id, cover_letter_style=style)
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


@router.callback_query(AutoparseSettingsCallback.filter(F.action == "cover_letter_style_custom"))
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
