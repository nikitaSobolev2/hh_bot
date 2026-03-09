"""Handlers for the Autoparse feature."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.modules.autoparse import services as ap_service
from src.bot.modules.autoparse.callbacks import (
    AutoparseCallback,
    AutoparseDownloadCallback,
    AutoparseSettingsCallback,
)
from src.bot.modules.autoparse.keyboards import (
    autoparse_detail_keyboard,
    autoparse_hub_keyboard,
    autoparse_list_keyboard,
    autoparse_settings_keyboard,
    cancel_keyboard,
    confirm_delete_keyboard,
    download_format_keyboard,
    template_list_keyboard,
)
from src.bot.modules.autoparse.states import AutoparseForm, AutoparseSettingsForm
from src.core.i18n import I18nContext
from src.models.user import User
from src.repositories.parsing import ParsingCompanyRepository

router = Router(name="autoparse")

_PER_PAGE = 5


# ── Hub ─────────────────────────────────────────────────────────────


async def show_autoparse_hub(callback: CallbackQuery, i18n: I18nContext) -> None:
    await callback.message.edit_text(
        f"<b>{i18n.get('autoparse-hub-title')}</b>\n\n{i18n.get('autoparse-hub-subtitle')}",
        reply_markup=autoparse_hub_keyboard(i18n),
    )


@router.callback_query(AutoparseCallback.filter(F.action == "hub"))
async def hub_handler(
    callback: CallbackQuery, callback_data: AutoparseCallback, i18n: I18nContext
) -> None:
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
    await callback.message.edit_text(
        i18n.get("autoparse-select-template"),
        reply_markup=template_list_keyboard(display, page, has_more, i18n),
    )
    await callback.answer()


@router.callback_query(AutoparseCallback.filter(F.action == "template_select"))
async def template_selected(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
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
    )
    await state.set_state(AutoparseForm.skills)
    await callback.message.edit_text(
        i18n.get("autoparse-enter-skills"),
        reply_markup=cancel_keyboard(i18n),
    )
    await callback.answer()


@router.callback_query(AutoparseCallback.filter(F.action == "skip_template"))
async def skip_template(callback: CallbackQuery, state: FSMContext, i18n: I18nContext) -> None:
    await state.set_state(AutoparseForm.vacancy_title)
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
async def receive_keywords(message: Message, state: FSMContext, i18n: I18nContext) -> None:
    await state.update_data(keyword_filter=message.text.strip())
    await state.set_state(AutoparseForm.skills)
    await message.answer(
        i18n.get("autoparse-enter-skills"),
        reply_markup=cancel_keyboard(i18n),
    )


@router.message(AutoparseForm.skills)
async def receive_skills(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    skills = message.text.strip()

    company = await ap_service.create_autoparse_company(
        session,
        user.id,
        data["vacancy_title"],
        data["search_url"],
        data.get("keyword_filter", ""),
        skills,
    )
    await state.clear()
    await message.answer(
        i18n.get("autoparse-created-success", id=str(company.id)),
        reply_markup=autoparse_hub_keyboard(i18n),
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
    page = callback_data.page
    companies, total = await ap_service.get_user_autoparse_companies(
        session, user.id, page, _PER_PAGE
    )
    if not companies and page == 0:
        await callback.message.edit_text(
            i18n.get("autoparse-empty-list"),
            reply_markup=autoparse_hub_keyboard(i18n),
        )
        await callback.answer()
        return

    has_more = (page + 1) * _PER_PAGE < total
    await callback.message.edit_text(
        i18n.get("autoparse-list-title"),
        reply_markup=autoparse_list_keyboard(companies, page, has_more, i18n),
    )
    await callback.answer()


# ── Detail ──────────────────────────────────────────────────────────


@router.callback_query(AutoparseCallback.filter(F.action == "detail"))
async def company_detail(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    company = await ap_service.get_autoparse_detail(session, callback_data.company_id)
    if not company:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return

    count = await ap_service.get_vacancy_count(session, company.id)
    text = ap_service.format_company_detail(company, count, i18n)
    await callback.message.edit_text(
        text,
        reply_markup=autoparse_detail_keyboard(company, i18n),
    )
    await callback.answer()


# ── Toggle ──────────────────────────────────────────────────────────


@router.callback_query(AutoparseCallback.filter(F.action == "toggle"))
async def toggle_company(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
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
        text = ap_service.format_company_detail(company, count, i18n)
        await callback.message.edit_text(
            text, reply_markup=autoparse_detail_keyboard(company, i18n)
        )


# ── Delete ──────────────────────────────────────────────────────────


@router.callback_query(AutoparseCallback.filter(F.action == "delete"))
async def delete_prompt(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    i18n: I18nContext,
) -> None:
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
    i18n: I18nContext,
) -> None:
    await ap_service.soft_delete_autoparse_company(session, callback_data.company_id)
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
    text = (
        f"<b>{i18n.get('autoparse-settings-title')}</b>\n\n"
        f"Work experience: {current.get('work_experience') or '—'}\n"
        f"Tech stack: {', '.join(current.get('tech_stack', [])) or '—'}\n"
        f"Send time: {current.get('send_time', '12:00')}"
    )
    await callback.message.edit_text(text, reply_markup=autoparse_settings_keyboard(i18n))
    await callback.answer()


@router.callback_query(AutoparseSettingsCallback.filter(F.action == "work_exp"))
async def settings_work_exp(callback: CallbackQuery, state: FSMContext, i18n: I18nContext) -> None:
    await state.set_state(AutoparseSettingsForm.work_experience)
    await callback.message.edit_text(
        i18n.get("autoparse-settings-work-exp") + "\n\n" + i18n.get("autoparse-enter-work-exp"),
        reply_markup=cancel_keyboard(i18n),
    )
    await callback.answer()


@router.message(AutoparseSettingsForm.work_experience)
async def receive_work_exp(
    message: Message, state: FSMContext, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    await ap_service.update_user_autoparse_settings(
        session, user.id, work_experience=message.text.strip()
    )
    await state.clear()
    await message.answer(
        i18n.get("autoparse-settings-saved"),
        reply_markup=autoparse_hub_keyboard(i18n),
    )


@router.callback_query(AutoparseSettingsCallback.filter(F.action == "send_time"))
async def settings_send_time(callback: CallbackQuery, state: FSMContext, i18n: I18nContext) -> None:
    await state.set_state(AutoparseSettingsForm.send_time)
    await callback.message.edit_text(
        i18n.get("autoparse-settings-send-time") + "\n\n" + i18n.get("autoparse-enter-send-time"),
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
    await callback.message.edit_text(
        i18n.get("autoparse-settings-tech-stack") + "\n\n" + i18n.get("autoparse-enter-tech-stack"),
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
