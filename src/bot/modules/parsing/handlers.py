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
)
from src.bot.modules.parsing.keyboards import (
    blacklist_choice_keyboard,
    cancel_keyboard,
    format_choice_keyboard,
    parsing_list_keyboard,
    style_selection_keyboard,
)
from src.bot.modules.parsing.states import ParsingForm
from src.models.user import User

router = Router(name="parsing")


async def show_parsing_list(
    callback: CallbackQuery, user: User, session: AsyncSession | None = None
) -> None:
    if session is None:
        from src.db.engine import async_session_factory

        async with async_session_factory() as session:
            return await show_parsing_list(callback, user, session)

    companies = await parsing_service.get_user_companies(session, user.id)

    if not companies:
        await callback.message.edit_text(
            "<b>📋 My Parsings</b>\n\nNo parsings yet. Start a new one!",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    await callback.message.edit_text(
        "<b>📋 My Parsings</b>",
        reply_markup=parsing_list_keyboard(companies),
    )


# --------------- FSM: new parsing flow ---------------


@router.callback_query(MenuCallback.filter(F.action == "new_parsing"))
async def fsm_start_parsing(
    callback: CallbackQuery, callback_data: MenuCallback, user: User, state: FSMContext
) -> None:
    await state.set_state(ParsingForm.vacancy_title)
    await callback.message.edit_text(
        "<b>🔍 New Parsing</b>\n\n"
        "Enter the vacancy title for your resume\n"
        "(e.g. Frontend Developer, Маркетолог):",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.message(ParsingForm.vacancy_title)
async def fsm_vacancy_title(message: Message, user: User, state: FSMContext) -> None:
    title = message.text.strip()
    if not title:
        await message.answer("Title cannot be empty. Please try again:")
        return

    await state.update_data(vacancy_title=title)
    await state.set_state(ParsingForm.search_url)
    await message.answer(
        "<b>Step 2/4</b>\n\n"
        "Enter the HH.ru search page URL\n"
        "(e.g. <code>https://hh.ru/search/vacancy?text=Frontend</code>):",
    )


@router.message(ParsingForm.search_url)
async def fsm_search_url(message: Message, user: User, state: FSMContext) -> None:
    from urllib.parse import urlparse

    url = message.text.strip()
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not hostname.endswith("hh.ru"):
        await message.answer(
            "Please enter a valid HH.ru URL\n"
            "(e.g. <code>https://hh.ru/search/vacancy?text=Python</code>)",
        )
        return

    await state.update_data(search_url=url)
    await state.set_state(ParsingForm.keyword_filter)
    await message.answer(
        "<b>Step 3/4</b>\n\n"
        "Enter keyword filter for vacancy titles\n"
        '("<code>|</code>" = OR, "<code>,</code>" = AND)\n'
        "Example: <code>frontend|backend,fullstack</code>\n\n"
        "Send <code>-</code> to skip filtering:",
    )


@router.message(ParsingForm.keyword_filter)
async def fsm_keyword_filter(message: Message, user: User, state: FSMContext) -> None:
    keyword = message.text.strip()
    if keyword == "-":
        keyword = ""

    await state.update_data(keyword_filter=keyword)
    await state.set_state(ParsingForm.target_count)
    await message.answer(
        "<b>Step 4/4</b>\n\nHow many vacancies to process?\n(e.g. 30):",
    )


@router.message(ParsingForm.target_count)
async def fsm_target_count(
    message: Message, user: User, state: FSMContext, session: AsyncSession
) -> None:
    text = message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("Please enter a positive number:")
        return

    count = int(text)
    if count > 200:
        await message.answer("Maximum is 200 vacancies. Please enter a smaller number:")
        return

    await state.update_data(target_count=count)
    data = await state.get_data()

    blacklisted_count = await parsing_service.get_blacklisted_count(
        session, user.id, data["vacancy_title"]
    )

    if blacklisted_count > 0:
        await state.set_state(ParsingForm.blacklist_check)
        await message.answer(
            f"<b>⚠️ Blacklist Check</b>\n\n"
            f"You have <b>{blacklisted_count}</b> blacklisted vacancies "
            f"for <b>{data['vacancy_title']}</b>.\n\n"
            f"Include previously parsed vacancies?",
            reply_markup=blacklist_choice_keyboard(),
        )
    else:
        await _confirm_and_launch(message, user, state, session, include_blacklisted=False)


@router.callback_query(ParsingCallback.filter(F.action.in_({"bl_skip", "bl_include"})))
async def fsm_blacklist_choice(
    callback: CallbackQuery,
    callback_data: ParsingCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    include = callback_data.action == "bl_include"
    await _confirm_and_launch(
        callback.message, user, state, session, include_blacklisted=include
    )
    await callback.answer()


async def _confirm_and_launch(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
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
    )

    parsing_service.dispatch_parsing_task(company_id, user.id, include_blacklisted)

    text = parsing_service.format_confirmation(data, include_blacklisted)
    await message.answer(text, reply_markup=back_to_menu_keyboard())


# --------------- parsing detail & format delivery ---------------


@router.callback_query(ParsingCallback.filter(F.action == "detail"))
async def parsing_detail(
    callback: CallbackQuery,
    callback_data: ParsingCallback,
    user: User,
    session: AsyncSession,
) -> None:
    company = await parsing_service.get_company_with_details(session, callback_data.company_id)

    if not company or company.user_id != user.id:
        await callback.answer("Not found", show_alert=True)
        return

    text = parsing_service.format_company_detail(company)
    kb = (
        format_choice_keyboard(company.id)
        if company.status == "completed"
        else back_to_menu_keyboard()
    )
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(FormatCallback.filter())
async def format_selection(
    callback: CallbackQuery,
    callback_data: FormatCallback,
    user: User,
    session: AsyncSession,
) -> None:
    company = await parsing_service.get_company_by_id(session, callback_data.company_id)
    if not company or company.user_id != user.id:
        await callback.answer("Not found", show_alert=True)
        return

    agg = await parsing_service.get_aggregated_result(session, callback_data.company_id)
    if not agg:
        await callback.answer("No results available yet", show_alert=True)
        return

    report = parsing_service.build_report(company, agg)
    fmt = callback_data.format

    if fmt == "message":
        text = report.generate_message()
        if len(text) > 4000:
            text = text[:3950] + "\n\n<i>...truncated. Download full report.</i>"
        await callback.message.edit_text(text, reply_markup=back_to_menu_keyboard())

    elif fmt in ("md", "txt"):
        content = report.generate_md() if fmt == "md" else report.generate_txt()
        doc = parsing_service.generate_document(
            content, f"report_{company.vacancy_title}_{company.id}.{fmt}"
        )
        await callback.message.answer_document(doc)
        await callback.answer("File sent")
        return

    await callback.answer()


# --------------- key phrases streaming ---------------


@router.callback_query(KeyPhrasesCallback.filter())
async def key_phrases_actions(
    callback: CallbackQuery,
    callback_data: KeyPhrasesCallback,
    user: User,
    session: AsyncSession,
) -> None:
    if callback_data.action == "start":
        await callback.message.edit_text(
            "<b>✨ Generate Key Phrases</b>\n\nSelect a style:",
            reply_markup=style_selection_keyboard(callback_data.company_id),
        )

    elif callback_data.action == "select_style":
        await callback.answer("Generating with AI streaming...")

        company = await parsing_service.get_company_by_id(session, callback_data.company_id)
        agg = await parsing_service.get_aggregated_result(session, callback_data.company_id)

        if not company or not agg or not agg.top_keywords:
            await callback.message.edit_text(
                "No keywords available. Run parsing first.",
                reply_markup=back_to_menu_keyboard(),
            )
            return

        await parsing_service.generate_key_phrases_stream(
            bot=callback.bot,
            session=session,
            company=company,
            agg=agg,
            style_key=callback_data.style,
            count=callback_data.count,
            chat_id=callback.message.chat.id,
        )
        return

    await callback.answer()


