import contextlib

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.callbacks.common import MenuCallback
from src.bot.keyboards.common import back_to_menu_keyboard
from src.bot.modules.parsing import services as parsing_service
from src.bot.modules.parsing.callbacks import (
    FormatCallback,
    IntegrateDutiesCallback,
    KeyPhrasesCallback,
    ParsingCallback,
    WorkExperienceCallback,
)
from src.bot.modules.parsing.keyboards import (
    back_to_company_keyboard,
    blacklist_choice_keyboard,
    cancel_add_company_keyboard,
    cancel_keyboard,
    compat_check_keyboard,
    count_input_keyboard,
    format_choice_keyboard,
    integrate_duties_apply_confirm_keyboard,
    integrate_duties_report_keyboard,
    language_selection_keyboard,
    parsing_hh_account_keyboard,
    parsing_list_keyboard,
    parsing_login_required_keyboard,
    parsing_pending_keyboard,
    per_company_count_keyboard,
    retry_compat_keyboard,
    retry_count_keyboard,
    retry_keyboard,
    style_selection_keyboard,
    work_experience_keyboard,
)
from src.bot.modules.parsing.states import ParsingForm
from src.bot.utils.limits import (
    get_compat_range,
    get_max_key_phrases_count,
    get_max_message_length,
    get_max_per_company_count,
    get_max_target_count,
    get_max_text_length,
    get_max_work_experiences,
)
from src.core.i18n import I18nContext
from src.models.parsing import AggregatedResult, ParsingCompany
from src.models.user import User
from src.repositories.hh_linked_account import HhLinkedAccountRepository
from src.services.hh.login_assist import login_assist_available
from src.services.hh.parse_browser_session import search_url_resume_id

router = Router(name="parsing")


async def show_parsing_list(
    callback: CallbackQuery,
    user: User,
    i18n: I18nContext,
    session: AsyncSession | None = None,
) -> None:
    if session is None:
        from src.db.engine import async_session_factory

        async with async_session_factory() as session:
            return await show_parsing_list(callback, user, i18n, session)

    companies = await parsing_service.get_user_companies(session, user.id)

    if not companies:
        await callback.message.edit_text(
            i18n.get("parsing-empty"),
            reply_markup=back_to_menu_keyboard(i18n),
        )
        return

    await callback.message.edit_text(
        i18n.get("parsing-list-title"),
        reply_markup=parsing_list_keyboard(companies, i18n),
    )


# --------------- FSM: new parsing flow ---------------


@router.callback_query(MenuCallback.filter(F.action == "new_parsing"))
async def fsm_start_parsing(
    callback: CallbackQuery,
    callback_data: MenuCallback,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.set_state(ParsingForm.vacancy_title)
    await callback.message.edit_text(
        f"{i18n.get('parsing-new-title')}\n\n{i18n.get('parsing-enter-title')}",
        reply_markup=cancel_keyboard(i18n),
    )
    await callback.answer()


@router.message(ParsingForm.vacancy_title)
async def fsm_vacancy_title(
    message: Message, user: User, state: FSMContext, i18n: I18nContext
) -> None:
    title = message.text.strip()
    if not title:
        await message.answer(i18n.get("parsing-title-empty"))
        return

    await state.update_data(vacancy_title=title)
    await state.set_state(ParsingForm.search_url)
    await message.answer(i18n.get("parsing-step2"))


@router.message(ParsingForm.search_url)
async def fsm_search_url(
    message: Message, user: User, state: FSMContext, i18n: I18nContext
) -> None:
    from urllib.parse import urlparse

    url = message.text.strip()
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not hostname.endswith("hh.ru"):
        await message.answer(i18n.get("parsing-invalid-url"))
        return

    await state.update_data(search_url=url)
    await state.set_state(ParsingForm.keyword_filter)
    await message.answer(i18n.get("parsing-step3"))


@router.message(ParsingForm.keyword_filter)
async def fsm_keyword_filter(
    message: Message, user: User, state: FSMContext, i18n: I18nContext
) -> None:
    keyword = message.text.strip()
    if keyword == "-":
        keyword = ""

    await state.update_data(keyword_filter=keyword)
    await _continue_parsing_hh_account_setup(
        message, state=state, user=user, session=None, i18n=i18n
    )


async def _proceed_to_target_count(
    target: CallbackQuery | Message,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.set_state(ParsingForm.target_count)
    text = i18n.get("parsing-step4")
    if isinstance(target, CallbackQuery):
        with contextlib.suppress(TelegramBadRequest):
            await target.message.edit_text(text)
        await target.answer()
        return
    await target.answer(text)


async def _continue_parsing_hh_account_setup(
    target: CallbackQuery | Message,
    *,
    state: FSMContext,
    user: User,
    session: AsyncSession | None,
    i18n: I18nContext,
) -> None:
    if session is None:
        from src.db.engine import async_session_factory

        async with async_session_factory() as session:
            return await _continue_parsing_hh_account_setup(
                target, state=state, user=user, session=session, i18n=i18n
            )

    data = await state.get_data()
    url = data.get("search_url") or ""
    if not search_url_resume_id(str(url)):
        await state.update_data(parse_hh_linked_account_id=None)
        await _proceed_to_target_count(target, state, i18n)
        return

    hh_repo = HhLinkedAccountRepository(session)
    accounts = await hh_repo.list_active_for_user(user.id)
    ready_accounts = [acc for acc in accounts if acc.browser_storage_enc]
    preferred_account_id = data.get("parse_hh_linked_account_id")

    if preferred_account_id:
        for acc in ready_accounts:
            if acc.id == preferred_account_id:
                await state.update_data(
                    parse_hh_linked_account_id=acc.id,
                    parsing_selected_hh_account_id=acc.id,
                )
                await _proceed_to_target_count(target, state, i18n)
                return

    if len(ready_accounts) == 1:
        await state.update_data(parse_hh_linked_account_id=ready_accounts[0].id)
        await _proceed_to_target_count(target, state, i18n)
        return

    await state.set_state(ParsingForm.hh_account)

    if len(accounts) > 1 or len(ready_accounts) > 1:
        text = i18n.get("parsing-hh-account-pick")
        kb = parsing_hh_account_keyboard(accounts, i18n)
        if isinstance(target, CallbackQuery):
            with contextlib.suppress(TelegramBadRequest):
                await target.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            await target.answer()
            return
        await target.answer(text, reply_markup=kb, parse_mode="HTML")
        return

    selected_account_id = accounts[0].id if accounts else None
    await state.update_data(parsing_selected_hh_account_id=selected_account_id)
    if accounts:
        label = accounts[0].label or accounts[0].hh_user_id
        text = i18n.get("autoparse-parse-login-for-account", label=label[:80])
    else:
        text = i18n.get("autoparse-parse-login-required")

    kb = parsing_login_required_keyboard(i18n)
    if isinstance(target, CallbackQuery):
        with contextlib.suppress(TelegramBadRequest):
            await target.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await target.answer()
        return
    await target.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(ParsingCallback.filter(F.action == "hh_account_skip"))
async def parsing_hh_account_skip(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.update_data(parse_hh_linked_account_id=None)
    await _proceed_to_target_count(callback, state, i18n)


@router.callback_query(ParsingCallback.filter(F.action == "hh_account_pick"))
async def parsing_hh_account_pick(
    callback: CallbackQuery,
    callback_data: ParsingCallback,
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
            parse_hh_linked_account_id=acc.id,
            parsing_selected_hh_account_id=acc.id,
        )
        await _proceed_to_target_count(callback, state, i18n)
        return

    await state.update_data(parsing_selected_hh_account_id=acc.id)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("autoparse-parse-login-for-account", label=(acc.label or acc.hh_user_id)[:80]),
            reply_markup=parsing_login_required_keyboard(i18n),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(ParsingCallback.filter(F.action == "hh_account_login_now"))
async def parsing_hh_account_login_now(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    i18n: I18nContext,
) -> None:
    if not login_assist_available():
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("autoparse-parse-no-login-assist"),
                reply_markup=parsing_login_required_keyboard(i18n),
            )
        await callback.answer()
        return

    from src.core.celery_async import run_celery_task
    from src.worker.tasks.hh_login_assist import hh_login_assist_task

    data = await state.get_data()
    selected_account_id = data.get("parsing_selected_hh_account_id")

    await callback.message.answer(
        i18n.get("autoparse-parse-login-followup"),
        reply_markup=parsing_login_required_keyboard(i18n),
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


@router.callback_query(ParsingCallback.filter(F.action == "hh_account_continue_after_login"))
async def parsing_hh_account_continue_after_login(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await _continue_parsing_hh_account_setup(
        callback, state=state, user=user, session=session, i18n=i18n
    )


@router.message(ParsingForm.target_count)
async def fsm_target_count(
    message: Message,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    text = message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer(i18n.get("parsing-positive-number"))
        return

    count = int(text)
    if count > get_max_target_count(user):
        await message.answer(i18n.get("parsing-max-50"))
        return

    await state.update_data(target_count=count)
    await state.set_state(ParsingForm.compat_check)
    await message.answer(
        i18n.get("parsing-compat-check-prompt"),
        reply_markup=compat_check_keyboard(i18n),
    )


@router.callback_query(ParsingCallback.filter(F.action == "compat_skip"))
async def fsm_compat_skip(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await state.update_data(use_compatibility_check=False, compatibility_threshold=None)
    await _proceed_to_blacklist_or_launch(callback.message, user, state, session, i18n)
    await callback.answer()


@router.callback_query(ParsingCallback.filter(F.action == "compat_yes"))
async def fsm_compat_yes(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.set_state(ParsingForm.compat_threshold)
    await callback.message.edit_text(
        i18n.get("parsing-compat-threshold-prompt"),
        reply_markup=cancel_keyboard(i18n),
    )
    await callback.answer()


@router.message(ParsingForm.compat_threshold)
async def fsm_compat_threshold(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    text = message.text.strip()
    compat_min, compat_max = get_compat_range(user)
    if not text.isdigit() or not (compat_min <= int(text) <= compat_max):
        await message.answer(i18n.get("parsing-compat-threshold-invalid"))
        return

    await state.update_data(use_compatibility_check=True, compatibility_threshold=int(text))
    await _proceed_to_blacklist_or_launch(message, user, state, session, i18n)


async def _proceed_to_blacklist_or_launch(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    blacklisted_count = await parsing_service.get_blacklisted_count(
        session, user.id, data["vacancy_title"]
    )

    if blacklisted_count > 0:
        await state.set_state(ParsingForm.blacklist_check)
        await message.answer(
            i18n.get(
                "parsing-blacklist-check",
                count=str(blacklisted_count),
                title=data["vacancy_title"],
            ),
            reply_markup=blacklist_choice_keyboard(i18n),
        )
    else:
        await _confirm_and_launch(message, user, state, session, i18n, include_blacklisted=False)


@router.callback_query(ParsingCallback.filter(F.action.in_({"bl_skip", "bl_include"})))
async def fsm_blacklist_choice(
    callback: CallbackQuery,
    callback_data: ParsingCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    include = callback_data.action == "bl_include"

    if "retry_company_id" in data:
        company = await _fetch_retry_company(session, user, data)
        if company is None:
            await state.clear()
            await callback.message.answer(i18n.get("parsing-not-found"))
            await callback.answer()
            return

        await state.clear()
        await _launch_retry(
            callback.message,
            user,
            session,
            i18n,
            company,
            data["retry_count"],
            use_compatibility_check=data.get("use_compatibility_check", False),
            compatibility_threshold=data.get("compatibility_threshold"),
            include_blacklisted=include,
        )
    else:
        await _confirm_and_launch(
            callback.message, user, state, session, i18n, include_blacklisted=include
        )
    await callback.answer()


async def _confirm_and_launch(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
    *,
    include_blacklisted: bool,
) -> None:
    data = await state.get_data()
    await state.clear()

    parse_hh_linked_account_id = data.get("parse_hh_linked_account_id")
    parse_hh_account_label = None
    if parse_hh_linked_account_id:
        from src.repositories.hh_linked_account import HhLinkedAccountRepository

        hh_repo = HhLinkedAccountRepository(session)
        hh_acc = await hh_repo.get_by_id(parse_hh_linked_account_id)
        if hh_acc and hh_acc.user_id == user.id:
            parse_hh_account_label = (hh_acc.label or hh_acc.hh_user_id)[:80]

    company_id = await parsing_service.create_parsing_company(
        session=session,
        user_id=user.id,
        vacancy_title=data["vacancy_title"],
        search_url=data["search_url"],
        keyword_filter=data.get("keyword_filter", ""),
        target_count=data["target_count"],
        use_compatibility_check=data.get("use_compatibility_check", False),
        compatibility_threshold=data.get("compatibility_threshold"),
        parse_hh_linked_account_id=parse_hh_linked_account_id,
    )

    await parsing_service.dispatch_parsing_task(
        company_id,
        user.id,
        include_blacklisted,
        telegram_chat_id=message.chat.id,
    )

    text = parsing_service.format_confirmation(
        {**data, "parse_hh_account_label": parse_hh_account_label},
        include_blacklisted,
        i18n,
    )
    await message.answer(text, reply_markup=back_to_menu_keyboard(i18n))


# --------------- parsing detail & format delivery ---------------


@router.callback_query(ParsingCallback.filter(F.action == "detail"))
async def parsing_detail(
    callback: CallbackQuery,
    callback_data: ParsingCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await state.clear()
    company = await parsing_service.get_company_with_details(session, callback_data.company_id)

    if not company or company.user_id != user.id:
        await callback.answer(i18n.get("parsing-not-found"), show_alert=True)
        return

    hh_account_label = None
    if company.parse_hh_linked_account_id:
        from src.repositories.hh_linked_account import HhLinkedAccountRepository

        hh_repo = HhLinkedAccountRepository(session)
        hh_acc = await hh_repo.get_by_id(company.parse_hh_linked_account_id)
        if hh_acc and hh_acc.user_id == user.id:
            hh_account_label = (hh_acc.label or hh_acc.hh_user_id)[:80]

    text = parsing_service.format_company_detail(
        company, i18n, hh_account_label=hh_account_label
    )
    has_integrated_duties = bool(
        company.aggregated_result and company.aggregated_result.integrated_duties
    )
    if company.status == "completed":
        kb = format_choice_keyboard(
            company.id,
            i18n,
            has_integrated_duties=has_integrated_duties,
        )
    elif company.status == "failed":
        kb = retry_keyboard(company.id, i18n)
    else:
        kb = parsing_pending_keyboard(company.id, i18n)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(ParsingCallback.filter(F.action == "retry"))
async def parsing_retry(
    callback: CallbackQuery,
    callback_data: ParsingCallback,
    user: User,
    session: AsyncSession,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    company = await parsing_service.get_company_for_user(session, callback_data.company_id, user.id)

    if not company:
        await callback.answer(i18n.get("parsing-not-found"), show_alert=True)
        return

    await state.set_state(ParsingForm.retry_count)
    await state.update_data(
        retry_company_id=company.id,
        retry_default_count=company.target_count,
    )
    await callback.message.edit_text(
        i18n.get("parsing-retry-count-prompt", default=str(company.target_count)),
        reply_markup=retry_count_keyboard(company.id, company.target_count, i18n),
    )
    await callback.answer()


@router.callback_query(ParsingCallback.filter(F.action == "retry_cancel"))
async def parsing_retry_cancel(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await state.clear()
    await show_parsing_list(callback, user, i18n, session)
    await callback.answer()


@router.callback_query(ParsingCallback.filter(F.action == "retry_use_default"))
async def parsing_retry_use_default(
    callback: CallbackQuery,
    callback_data: ParsingCallback,
    user: User,
    session: AsyncSession,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()

    company = await parsing_service.get_company_for_user(session, callback_data.company_id, user.id)
    if not company:
        await callback.answer(i18n.get("parsing-not-found"), show_alert=True)
        return

    target_count = data.get("retry_default_count", company.target_count)
    await state.update_data(retry_count=target_count)
    await state.set_state(ParsingForm.retry_compat_check)
    await callback.message.edit_text(
        i18n.get("parsing-retry-compat-prompt"),
        reply_markup=retry_compat_keyboard(i18n),
    )
    await callback.answer()


@router.message(ParsingForm.retry_count)
async def fsm_retry_count(
    message: Message,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    text = message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer(i18n.get("parsing-positive-number"))
        return

    count = int(text)
    if count > get_max_target_count(user):
        await message.answer(i18n.get("parsing-max-50"))
        return

    await state.update_data(retry_count=count)
    await state.set_state(ParsingForm.retry_compat_check)
    await message.answer(
        i18n.get("parsing-retry-compat-prompt"),
        reply_markup=retry_compat_keyboard(i18n),
    )


@router.callback_query(ParsingCallback.filter(F.action == "retry_compat_skip"))
async def fsm_retry_compat_skip(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    company = await _fetch_retry_company(session, user, data)
    if company is None:
        await state.clear()
        await callback.message.answer(i18n.get("parsing-not-found"))
        await callback.answer()
        return

    await _proceed_to_retry_blacklist_or_launch(
        callback.message,
        user,
        state,
        session,
        i18n,
        company,
        data["retry_count"],
        use_compatibility_check=False,
        compatibility_threshold=None,
    )
    await callback.answer()


@router.callback_query(ParsingCallback.filter(F.action == "retry_compat_yes"))
async def fsm_retry_compat_yes(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.set_state(ParsingForm.retry_compat_threshold)
    await callback.message.edit_text(
        i18n.get("parsing-compat-threshold-prompt"),
        reply_markup=cancel_keyboard(i18n),
    )
    await callback.answer()


@router.message(ParsingForm.retry_compat_threshold)
async def fsm_retry_compat_threshold(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    text = message.text.strip()
    compat_min, compat_max = get_compat_range(user)
    if not text.isdigit() or not (compat_min <= int(text) <= compat_max):
        await message.answer(i18n.get("parsing-compat-threshold-invalid"))
        return

    threshold = int(text)
    data = await state.get_data()
    company = await _fetch_retry_company(session, user, data)
    if company is None:
        await state.clear()
        await message.answer(i18n.get("parsing-not-found"))
        return

    await _proceed_to_retry_blacklist_or_launch(
        message,
        user,
        state,
        session,
        i18n,
        company,
        data["retry_count"],
        use_compatibility_check=True,
        compatibility_threshold=threshold,
    )


async def _fetch_retry_company(
    session: AsyncSession,
    user: "User",  # noqa: F821
    state_data: dict,
) -> "ParsingCompany | None":  # noqa: F821
    company_id = state_data.get("retry_company_id")
    if not company_id:
        return None
    return await parsing_service.get_company_for_user(session, company_id, user.id)


async def _proceed_to_retry_blacklist_or_launch(
    message: Message,
    user: "User",  # noqa: F821
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
    company: "ParsingCompany",  # noqa: F821
    retry_count: int,
    *,
    use_compatibility_check: bool = False,
    compatibility_threshold: int | None = None,
) -> None:
    blacklisted_count = await parsing_service.get_blacklisted_count(
        session, user.id, company.vacancy_title
    )
    if blacklisted_count > 0:
        await state.update_data(
            retry_company_id=company.id,
            retry_count=retry_count,
            use_compatibility_check=use_compatibility_check,
            compatibility_threshold=compatibility_threshold,
        )
        await state.set_state(ParsingForm.blacklist_check)
        await message.answer(
            i18n.get(
                "parsing-blacklist-check",
                count=str(blacklisted_count),
                title=company.vacancy_title,
            ),
            reply_markup=blacklist_choice_keyboard(i18n),
        )
    else:
        await state.clear()
        await _launch_retry(
            message,
            user,
            session,
            i18n,
            company,
            retry_count,
            use_compatibility_check=use_compatibility_check,
            compatibility_threshold=compatibility_threshold,
            include_blacklisted=False,
        )


async def _launch_retry(
    message: Message,
    user: "User",  # noqa: F821
    session: AsyncSession,
    i18n: I18nContext,
    company: "ParsingCompany",  # noqa: F821
    target_count: int,
    *,
    use_compatibility_check: bool = False,
    compatibility_threshold: int | None = None,
    include_blacklisted: bool = False,
) -> None:
    max_count = get_max_target_count(user)
    if target_count > max_count:
        target_count = max_count
    new_company_id = await parsing_service.clone_and_dispatch(
        session,
        company.id,
        user.id,
        telegram_chat_id=message.chat.id,
        target_count=target_count,
        use_compatibility_check=use_compatibility_check,
        compatibility_threshold=compatibility_threshold,
        include_blacklisted=include_blacklisted,
    )
    filter_val = company.keyword_filter or i18n.get("detail-filter-none")
    text = i18n.get(
        "parsing-restarted",
        title=company.vacancy_title,
        count=str(target_count),
        filter=filter_val,
        new_id=str(new_company_id),
    )
    await message.answer(text, reply_markup=back_to_menu_keyboard(i18n))


@router.callback_query(ParsingCallback.filter(F.action == "delete"))
async def parsing_delete(
    callback: CallbackQuery,
    callback_data: ParsingCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    deleted = await parsing_service.soft_delete_parsing(session, callback_data.company_id, user.id)
    if not deleted:
        await callback.answer(i18n.get("parsing-not-found"), show_alert=True)
        return
    await callback.answer(i18n.get("parsing-deleted"))
    await show_parsing_list(callback, user, i18n, session)


@router.callback_query(FormatCallback.filter())
async def format_selection(
    callback: CallbackQuery,
    callback_data: FormatCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    company = await parsing_service.get_company_for_user(session, callback_data.company_id, user.id)
    if not company:
        await callback.answer(i18n.get("parsing-not-found"), show_alert=True)
        return

    agg = await parsing_service.get_aggregated_result(session, callback_data.company_id)
    if not agg:
        await callback.answer(i18n.get("parsing-no-results"), show_alert=True)
        return

    locale = user.language_code or "ru"
    report = parsing_service.build_report(company, agg, locale=locale)
    fmt = callback_data.format

    if fmt == "message":
        text = report.generate_message()
        max_len = get_max_message_length(user, "default")
        if len(text) > max_len:
            text = text[: max_len - 50] + "\n\n" + i18n.get("parsing-truncated")
        await callback.message.edit_text(
            text, reply_markup=back_to_company_keyboard(callback_data.company_id, i18n)
        )

    elif fmt in ("md", "txt"):
        content = report.generate_md() if fmt == "md" else report.generate_txt()
        doc = parsing_service.generate_document(
            content, f"report_{company.vacancy_title}_{company.id}.{fmt}"
        )
        await callback.message.answer_document(doc)
        await callback.answer(i18n.get("parsing-file-sent"))
        return

    await callback.answer()


# --------------- work experience ---------------


async def _show_work_experience_step(
    message,
    user: User,
    company_id: int,
    session: AsyncSession,
    i18n: I18nContext,
    *,
    edit: bool = True,
) -> None:
    experiences = await parsing_service.get_active_work_experiences(session, user.id)

    text = f"{i18n.get('keyphrase-title')}\n\n{i18n.get('work-exp-prompt')}"
    if experiences:
        lines = [f"  \u2022 <b>{e.company_name}</b> \u2014 {e.stack}" for e in experiences]
        text += "\n\n" + "\n".join(lines)

    kb = work_experience_keyboard(company_id, experiences, i18n, is_admin=user.is_admin)
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


@router.callback_query(KeyPhrasesCallback.filter(F.action == "start"))
async def key_phrases_start(
    callback: CallbackQuery,
    callback_data: KeyPhrasesCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await state.clear()
    await _show_work_experience_step(
        callback.message, user, callback_data.company_id, session, i18n
    )
    await callback.answer()


@router.callback_query(WorkExperienceCallback.filter(F.action == "add"))
async def work_exp_add(
    callback: CallbackQuery,
    callback_data: WorkExperienceCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    active_count = await parsing_service.count_active_work_experiences(session, user.id)
    if active_count >= get_max_work_experiences(user):
        await callback.answer(i18n.get("work-exp-max-reached"), show_alert=True)
        return

    await state.set_state(ParsingForm.work_exp_company_name)
    await state.update_data(we_company_id=callback_data.company_id)
    await callback.message.edit_text(
        i18n.get("work-exp-enter-name"),
        reply_markup=cancel_add_company_keyboard(callback_data.company_id, i18n),
    )
    await callback.answer()


@router.message(ParsingForm.work_exp_company_name)
async def fsm_work_exp_company_name(
    message: Message,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    name = message.text.strip()
    max_len = get_max_text_length(user, "company_name")
    if not name or len(name) > max_len:
        await message.answer(i18n.get("work-exp-name-invalid"))
        return

    data = await state.get_data()
    await state.update_data(we_company_name=name)
    await state.set_state(ParsingForm.work_exp_stack)
    await message.answer(
        i18n.get("work-exp-enter-stack", company=name),
        reply_markup=cancel_add_company_keyboard(data["we_company_id"], i18n),
    )


@router.message(ParsingForm.work_exp_stack)
async def fsm_work_exp_stack(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    stack = message.text.strip()
    if not stack:
        await message.answer(i18n.get("work-exp-stack-invalid"))
        return

    data = await state.get_data()
    company_id = data["we_company_id"]
    company_name = data["we_company_name"]
    await state.clear()

    await parsing_service.add_work_experience(session, user.id, company_name, stack)

    await _show_work_experience_step(message, user, company_id, session, i18n, edit=False)


@router.callback_query(WorkExperienceCallback.filter(F.action == "cancel_add"))
async def work_exp_cancel_add(
    callback: CallbackQuery,
    callback_data: WorkExperienceCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await state.clear()
    await _show_work_experience_step(
        callback.message, user, callback_data.company_id, session, i18n
    )
    await callback.answer()


@router.callback_query(WorkExperienceCallback.filter(F.action == "remove"))
async def work_exp_remove(
    callback: CallbackQuery,
    callback_data: WorkExperienceCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    deactivated = await parsing_service.deactivate_work_experience(
        session, callback_data.work_exp_id, user.id
    )
    if not deactivated:
        await callback.answer(i18n.get("parsing-not-found"), show_alert=True)
        return
    await _show_work_experience_step(
        callback.message, user, callback_data.company_id, session, i18n
    )
    await callback.answer()


@router.callback_query(WorkExperienceCallback.filter(F.action == "skip"))
async def work_exp_skip(
    callback: CallbackQuery,
    callback_data: WorkExperienceCallback,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.set_state(ParsingForm.key_phrases_count)
    await state.update_data(kp_company_id=callback_data.company_id)
    await callback.message.edit_text(
        f"{i18n.get('keyphrase-title')}\n\n{i18n.get('keyphrase-count-prompt')}",
        reply_markup=count_input_keyboard(callback_data.company_id, i18n),
    )
    await callback.answer()


@router.callback_query(WorkExperienceCallback.filter(F.action == "continue"))
async def work_exp_continue(
    callback: CallbackQuery,
    callback_data: WorkExperienceCallback,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.set_state(ParsingForm.key_phrases_per_company_count)
    await state.update_data(kp_company_id=callback_data.company_id)
    await callback.message.edit_text(
        f"{i18n.get('keyphrase-title')}\n\n{i18n.get('keyphrase-per-company-count')}",
        reply_markup=per_company_count_keyboard(callback_data.company_id, i18n),
    )
    await callback.answer()


@router.message(ParsingForm.key_phrases_per_company_count)
async def fsm_per_company_count(
    message: Message,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    text = message.text.strip()
    if not text.isdigit() or int(text) < 1:
        await message.answer(i18n.get("keyphrase-enter-number"))
        return

    count = int(text)
    if count > get_max_per_company_count(user):
        await message.answer(i18n.get("keyphrase-max-8"))
        return

    data = await state.get_data()
    company_id = data["kp_company_id"]
    await state.clear()

    await message.answer(
        f"{i18n.get('keyphrase-title')}\n\n{i18n.get('keyphrase-select-lang')}",
        reply_markup=language_selection_keyboard(
            company_id, count, i18n, mode="w", is_admin=user.is_admin
        ),
    )


# --------------- key phrases: count / language / style / dispatch ---------------


@router.callback_query(KeyPhrasesCallback.filter(F.action == "skip_count"))
async def key_phrases_skip_count(
    callback: CallbackQuery,
    callback_data: KeyPhrasesCallback,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.clear()
    await callback.message.edit_text(
        f"{i18n.get('keyphrase-title')}\n\n{i18n.get('keyphrase-select-lang')}",
        reply_markup=language_selection_keyboard(
            callback_data.company_id, 0, i18n, is_admin=user.is_admin
        ),
    )
    await callback.answer()


@router.message(ParsingForm.key_phrases_count)
async def fsm_key_phrases_count(
    message: Message, user: User, state: FSMContext, i18n: I18nContext
) -> None:
    text = message.text.strip()
    if not text.isdigit() or int(text) < 1:
        await message.answer(i18n.get("keyphrase-enter-number"))
        return

    count = int(text)
    if count > get_max_key_phrases_count(user):
        await message.answer(i18n.get("keyphrase-max-30"))
        return

    data = await state.get_data()
    company_id = data["kp_company_id"]
    await state.clear()

    await message.answer(
        f"{i18n.get('keyphrase-title')}\n\n{i18n.get('keyphrase-select-lang')}",
        reply_markup=language_selection_keyboard(company_id, count, i18n, is_admin=user.is_admin),
    )


@router.callback_query(KeyPhrasesCallback.filter(F.action == "lang_manual"))
async def key_phrases_lang_manual(
    callback: CallbackQuery,
    callback_data: KeyPhrasesCallback,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    if not user.is_admin:
        await callback.answer(i18n.get("access-denied"), show_alert=True)
        return
    await state.set_state(ParsingForm.lang_manual)
    await state.update_data(
        kp_company_id=callback_data.company_id,
        kp_count=callback_data.count,
        kp_mode=callback_data.mode or "",
    )
    await callback.message.edit_text(
        i18n.get("parsing-enter-lang-manual"),
        reply_markup=cancel_keyboard(i18n),
    )
    await callback.answer()


@router.message(ParsingForm.lang_manual)
async def fsm_lang_manual(
    message: Message,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    if not user.is_admin:
        await state.clear()
        return
    lang = (message.text or "").strip()
    if not lang:
        await message.answer(i18n.get("parsing-enter-lang-manual"))
        return
    data = await state.get_data()
    await state.clear()
    await message.answer(
        f"{i18n.get('keyphrase-title')}\n\n{i18n.get('keyphrase-select-style')}",
        reply_markup=style_selection_keyboard(
            data["kp_company_id"],
            i18n,
            data["kp_count"],
            lang,
            data.get("kp_mode", ""),
            is_admin=user.is_admin,
        ),
    )


@router.callback_query(KeyPhrasesCallback.filter(F.action == "select_lang"))
async def key_phrases_select_lang(
    callback: CallbackQuery,
    callback_data: KeyPhrasesCallback,
    user: User,
    i18n: I18nContext,
) -> None:
    await callback.message.edit_text(
        f"{i18n.get('keyphrase-title')}\n\n{i18n.get('keyphrase-select-style')}",
        reply_markup=style_selection_keyboard(
            callback_data.company_id,
            i18n,
            callback_data.count,
            callback_data.lang,
            mode=callback_data.mode,
            is_admin=user.is_admin,
        ),
    )
    await callback.answer()


@router.callback_query(KeyPhrasesCallback.filter(F.action == "style_manual"))
async def key_phrases_style_manual(
    callback: CallbackQuery,
    callback_data: KeyPhrasesCallback,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    if not user.is_admin:
        await callback.answer(i18n.get("access-denied"), show_alert=True)
        return
    await state.set_state(ParsingForm.style_manual)
    await state.update_data(
        kp_company_id=callback_data.company_id,
        kp_count=callback_data.count,
        kp_lang=callback_data.lang or "ru",
        kp_mode=callback_data.mode or "",
    )
    await callback.message.edit_text(
        i18n.get("parsing-enter-style-manual"),
        reply_markup=cancel_keyboard(i18n),
    )
    await callback.answer()


@router.message(ParsingForm.style_manual)
async def fsm_style_manual(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    if not user.is_admin:
        await state.clear()
        return
    style = (message.text or "").strip()
    if not style:
        await message.answer(i18n.get("parsing-enter-style-manual"))
        return
    data = await state.get_data()
    await state.clear()
    company = await parsing_service.get_company_for_user(session, data["kp_company_id"], user.id)
    agg = await parsing_service.get_aggregated_result(session, data["kp_company_id"])
    if not company or not agg or not agg.top_keywords:
        await message.answer(
            i18n.get("keyphrase-no-keywords"),
            reply_markup=back_to_menu_keyboard(i18n),
        )
        return
    await parsing_service.dispatch_key_phrases_task(
        company_id=data["kp_company_id"],
        user_id=user.id,
        style_key=style,
        count=data["kp_count"],
        lang=data["kp_lang"],
        chat_id=message.chat.id,
        mode=data["kp_mode"],
    )
    await message.answer(i18n.get("keyphrase-generating"))


@router.callback_query(KeyPhrasesCallback.filter(F.action == "select_style"))
async def key_phrases_select_style(
    callback: CallbackQuery,
    callback_data: KeyPhrasesCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    company = await parsing_service.get_company_for_user(session, callback_data.company_id, user.id)
    agg = await parsing_service.get_aggregated_result(session, callback_data.company_id)

    if not company or not agg or not agg.top_keywords:
        await callback.message.edit_text(
            i18n.get("keyphrase-no-keywords"),
            reply_markup=back_to_menu_keyboard(i18n),
        )
        await callback.answer()
        return

    await parsing_service.dispatch_key_phrases_task(
        company_id=callback_data.company_id,
        user_id=user.id,
        style_key=callback_data.style,
        count=callback_data.count,
        lang=callback_data.lang,
        chat_id=callback.message.chat.id,
        mode=callback_data.mode,
    )
    await callback.message.edit_text(i18n.get("keyphrase-generating"))
    await callback.answer()


# --------------- integrate duties into work experience ---------------


async def _show_integrated_duties_report(
    message,
    *,
    company_id: int,
    payload: dict,
    user: User,
    i18n: I18nContext,
    page: int = 0,
    completed_header: str | None = None,
) -> None:
    from src.bot.utils.limits import get_max_message_length
    from src.services.ai.duties_integration import get_integrated_duties_report_page

    locale = user.language_code or "ru"
    max_len = get_max_message_length(user, "default")
    report_text, total_pages = get_integrated_duties_report_page(
        payload,
        locale,
        page=page,
        max_len=max_len,
        completed_header=completed_header,
    )
    await message.edit_text(
        report_text,
        reply_markup=integrate_duties_report_keyboard(
            company_id,
            i18n,
            page=page,
            total_pages=total_pages,
        ),
    )


async def _validate_integrate_duties_prerequisites(
    session: AsyncSession,
    user: User,
    company_id: int,
    i18n: I18nContext,
) -> tuple[ParsingCompany | None, AggregatedResult | None, str | None]:
    company = await parsing_service.get_company_for_user(session, company_id, user.id)
    if not company or company.status != "completed":
        return None, None, i18n.get("parsing-not-found")

    agg = await parsing_service.get_aggregated_result(session, company_id)
    if not agg or not parsing_service.get_top_keywords(agg):
        return company, agg, i18n.get("integrate-duties-error-no-keywords")

    work_experiences = await parsing_service.get_work_experiences_with_duties(session, user.id)
    if not work_experiences:
        return company, agg, i18n.get("integrate-duties-error-no-duties")

    return company, agg, None


@router.callback_query(IntegrateDutiesCallback.filter(F.action == "start"))
async def integrate_duties_start(
    callback: CallbackQuery,
    callback_data: IntegrateDutiesCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    _, _, error = await _validate_integrate_duties_prerequisites(
        session,
        user,
        callback_data.company_id,
        i18n,
    )
    if error:
        await callback.answer(error, show_alert=True)
        return

    await parsing_service.dispatch_integrate_duties_task(
        company_id=callback_data.company_id,
        user_id=user.id,
        chat_id=callback.message.chat.id,
    )
    await callback.message.edit_text(i18n.get("integrate-duties-generating"))
    await callback.answer()


@router.callback_query(IntegrateDutiesCallback.filter(F.action == "view"))
async def integrate_duties_view(
    callback: CallbackQuery,
    callback_data: IntegrateDutiesCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    company = await parsing_service.get_company_for_user(session, callback_data.company_id, user.id)
    agg = await parsing_service.get_aggregated_result(session, callback_data.company_id)
    if not company or not agg or not agg.integrated_duties:
        await callback.answer(i18n.get("integrate-duties-error-not-found"), show_alert=True)
        return

    await _show_integrated_duties_report(
        callback.message,
        company_id=callback_data.company_id,
        payload=agg.integrated_duties,
        user=user,
        i18n=i18n,
        page=callback_data.page,
    )
    await callback.answer()


@router.callback_query(IntegrateDutiesCallback.filter(F.action == "apply"))
async def integrate_duties_apply(
    callback: CallbackQuery,
    callback_data: IntegrateDutiesCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    agg = await parsing_service.get_aggregated_result(session, callback_data.company_id)
    if not agg or not agg.integrated_duties:
        await callback.answer(i18n.get("integrate-duties-error-not-found"), show_alert=True)
        return

    await callback.message.edit_text(
        i18n.get("integrate-duties-apply-confirm"),
        reply_markup=integrate_duties_apply_confirm_keyboard(callback_data.company_id, i18n),
    )
    await callback.answer()


@router.callback_query(IntegrateDutiesCallback.filter(F.action == "apply_confirm"))
async def integrate_duties_apply_confirm(
    callback: CallbackQuery,
    callback_data: IntegrateDutiesCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    company = await parsing_service.get_company_for_user(session, callback_data.company_id, user.id)
    agg = await parsing_service.get_aggregated_result(session, callback_data.company_id)
    if not company or not agg or not agg.integrated_duties:
        await callback.answer(i18n.get("integrate-duties-error-not-found"), show_alert=True)
        return

    updated = await parsing_service.apply_integrated_duties(
        session,
        user.id,
        agg.integrated_duties,
    )
    if updated == 0:
        await callback.answer(i18n.get("integrate-duties-apply-failed"), show_alert=True)
        return

    await callback.message.edit_text(
        i18n.get("integrate-duties-apply-success", count=str(updated)),
        reply_markup=format_choice_keyboard(
            company.id,
            i18n,
            has_integrated_duties=True,
        ),
    )
    await callback.answer()
