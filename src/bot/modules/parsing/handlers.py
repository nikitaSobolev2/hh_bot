from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.callbacks.common import MenuCallback
from src.bot.keyboards.common import back_to_menu_keyboard
from src.bot.modules.parsing import services as parsing_service
from src.bot.modules.parsing.callbacks import (
    FormatCallback,
    KeyPhrasesCallback,
    ParsingCallback,
    WorkExperienceCallback,
)
from src.bot.modules.parsing.keyboards import (
    MAX_WORK_EXPERIENCES,
    back_to_company_keyboard,
    blacklist_choice_keyboard,
    cancel_add_company_keyboard,
    cancel_keyboard,
    compat_check_keyboard,
    count_input_keyboard,
    format_choice_keyboard,
    language_selection_keyboard,
    parsing_list_keyboard,
    per_company_count_keyboard,
    retry_compat_keyboard,
    retry_count_keyboard,
    retry_keyboard,
    style_selection_keyboard,
    work_experience_keyboard,
)
from src.bot.modules.parsing.states import ParsingForm
from src.core.i18n import I18nContext
from src.models.user import User

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
    await state.set_state(ParsingForm.target_count)
    await message.answer(i18n.get("parsing-step4"))


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
    if count > 200:
        await message.answer(i18n.get("parsing-max-200"))
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
    if not text.isdigit() or not (1 <= int(text) <= 100):
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
    include = callback_data.action == "bl_include"
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

    company_id = await parsing_service.create_parsing_company(
        session=session,
        user_id=user.id,
        vacancy_title=data["vacancy_title"],
        search_url=data["search_url"],
        keyword_filter=data.get("keyword_filter", ""),
        target_count=data["target_count"],
        use_compatibility_check=data.get("use_compatibility_check", False),
        compatibility_threshold=data.get("compatibility_threshold"),
    )

    parsing_service.dispatch_parsing_task(
        company_id,
        user.id,
        include_blacklisted,
        telegram_chat_id=message.chat.id,
    )

    text = parsing_service.format_confirmation(data, include_blacklisted, i18n)
    await message.answer(text, reply_markup=back_to_menu_keyboard(i18n))


# --------------- parsing detail & format delivery ---------------


@router.callback_query(ParsingCallback.filter(F.action == "detail"))
async def parsing_detail(
    callback: CallbackQuery,
    callback_data: ParsingCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    company = await parsing_service.get_company_with_details(session, callback_data.company_id)

    if not company or company.user_id != user.id:
        await callback.answer(i18n.get("parsing-not-found"), show_alert=True)
        return

    text = parsing_service.format_company_detail(company, i18n)
    if company.status == "completed":
        kb = format_choice_keyboard(company.id, i18n)
    elif company.status == "failed":
        kb = retry_keyboard(company.id, i18n)
    else:
        kb = back_to_menu_keyboard(i18n)
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
    company = await parsing_service.get_company_by_id(session, callback_data.company_id)

    if not company or company.user_id != user.id:
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

    company = await parsing_service.get_company_by_id(session, callback_data.company_id)
    if not company or company.user_id != user.id:
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
    if count > 200:
        await message.answer(i18n.get("parsing-max-200"))
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
    await state.clear()

    company = await _fetch_retry_company(session, user, data)
    if company is None:
        await callback.message.answer(i18n.get("parsing-not-found"))
        await callback.answer()
        return

    await _launch_retry(
        callback.message,
        user,
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
    if not text.isdigit() or not (1 <= int(text) <= 100):
        await message.answer(i18n.get("parsing-compat-threshold-invalid"))
        return

    threshold = int(text)
    data = await state.get_data()
    await state.clear()

    company = await _fetch_retry_company(session, user, data)
    if company is None:
        await message.answer(i18n.get("parsing-not-found"))
        return

    await _launch_retry(
        message,
        user,
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
    company = await parsing_service.get_company_by_id(session, company_id)
    if not company or company.user_id != user.id:
        return None
    return company


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
) -> None:
    new_company_id = await parsing_service.clone_and_dispatch(
        session,
        company.id,
        user.id,
        telegram_chat_id=message.chat.id,
        target_count=target_count,
        use_compatibility_check=use_compatibility_check,
        compatibility_threshold=compatibility_threshold,
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


@router.callback_query(FormatCallback.filter())
async def format_selection(
    callback: CallbackQuery,
    callback_data: FormatCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    company = await parsing_service.get_company_by_id(session, callback_data.company_id)
    if not company or company.user_id != user.id:
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
        if len(text) > 4000:
            text = text[:3950] + "\n\n" + i18n.get("parsing-truncated")
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

    kb = work_experience_keyboard(company_id, experiences, i18n)
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
    if active_count >= MAX_WORK_EXPERIENCES:
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
    if not name or len(name) > 255:
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
    if count > 8:
        await message.answer(i18n.get("keyphrase-max-8"))
        return

    data = await state.get_data()
    company_id = data["kp_company_id"]
    await state.clear()

    await message.answer(
        f"{i18n.get('keyphrase-title')}\n\n{i18n.get('keyphrase-select-lang')}",
        reply_markup=language_selection_keyboard(company_id, count, i18n, mode="w"),
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
        reply_markup=language_selection_keyboard(callback_data.company_id, 0, i18n),
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
    if count > 30:
        await message.answer(i18n.get("keyphrase-max-30"))
        return

    data = await state.get_data()
    company_id = data["kp_company_id"]
    await state.clear()

    await message.answer(
        f"{i18n.get('keyphrase-title')}\n\n{i18n.get('keyphrase-select-lang')}",
        reply_markup=language_selection_keyboard(company_id, count, i18n),
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
        ),
    )
    await callback.answer()


@router.callback_query(KeyPhrasesCallback.filter(F.action == "select_style"))
async def key_phrases_select_style(
    callback: CallbackQuery,
    callback_data: KeyPhrasesCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    company = await parsing_service.get_company_by_id(session, callback_data.company_id)
    agg = await parsing_service.get_aggregated_result(session, callback_data.company_id)

    if not company or not agg or not agg.top_keywords:
        await callback.message.edit_text(
            i18n.get("keyphrase-no-keywords"),
            reply_markup=back_to_menu_keyboard(i18n),
        )
        await callback.answer()
        return

    parsing_service.dispatch_key_phrases_task(
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
