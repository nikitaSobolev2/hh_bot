from datetime import datetime

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.callbacks.common import MenuCallback
from src.bot.keyboards.common import main_menu_admin_keyboard, main_menu_keyboard
from src.bot.modules.start.services import process_referral
from src.core.i18n import I18nContext
from src.models.user import User

router = Router(name="start")

_HANDLED_IN_START = {
    "main",
    "profile",
    "settings",
    "my_parsings",
    "my_interviews",
    "autoparse",
    "admin",
    "generate_vacancy_prep_query",
    "support",
    "work_experience",
    "achievements",
    "interview_qa",
    "vacancy_summary",
    "resume",
    "cover_letter",
}


def _menu_keyboard(user: User, i18n: I18nContext) -> object:
    return main_menu_admin_keyboard(i18n) if user.is_admin else main_menu_keyboard(i18n)


@router.message(CommandStart(deep_link=True))
async def cmd_start_deep_link(
    message: Message, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    args = message.text.split(maxsplit=1)
    deep_link = args[1] if len(args) > 1 else ""

    if deep_link.startswith("ref_"):
        await process_referral(session, user, deep_link[4:])

    await message.answer(i18n.get("welcome"), reply_markup=_menu_keyboard(user, i18n))


@router.message(CommandStart())
async def cmd_start(message: Message, user: User, i18n: I18nContext) -> None:
    await message.answer(i18n.get("welcome"), reply_markup=_menu_keyboard(user, i18n))


@router.callback_query(MenuCallback.filter(F.action.in_(_HANDLED_IN_START)))
async def menu_navigation(
    callback: CallbackQuery,
    callback_data: MenuCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await callback.answer()
    action = callback_data.action
    handler = _MENU_DISPATCH.get(action)
    if handler:
        await handler(callback, user, session, i18n)


async def _handle_main(
    callback: CallbackQuery, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    await callback.message.edit_text(i18n.get("welcome"), reply_markup=_menu_keyboard(user, i18n))


async def _handle_profile(
    callback: CallbackQuery, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    from src.bot.modules.profile.handlers import show_profile

    await show_profile(callback, user, i18n)


async def _handle_settings(
    callback: CallbackQuery, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    from src.bot.modules.user_settings.handlers import show_settings

    await show_settings(callback, i18n)


async def _handle_my_parsings(
    callback: CallbackQuery, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    from src.bot.modules.parsing.handlers import show_parsing_list

    await show_parsing_list(callback, user, i18n)


async def _handle_autoparse(
    callback: CallbackQuery, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    from src.bot.modules.autoparse.handlers import show_autoparse_hub

    await show_autoparse_hub(callback, i18n)


async def _handle_admin(
    callback: CallbackQuery, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    if not user.is_admin:
        await callback.answer(i18n.get("access-denied"), show_alert=True)
        return
    from src.bot.modules.admin.handlers import show_admin_panel

    await show_admin_panel(callback, i18n)


async def _handle_generate_vacancy_prep_query(
    callback: CallbackQuery, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    if not user.is_admin:
        await callback.answer(i18n.get("access-denied"), show_alert=True)
        return
    from src.bot.modules.admin.services import build_vacancy_prep_query

    query_text = await build_vacancy_prep_query(session, user)
    filename = f"vacancy_prep_query_{user.id}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    doc = BufferedInputFile(query_text.encode("utf-8"), filename=filename)
    await callback.message.answer_document(doc)
    await callback.answer(i18n.get("admin-vacancy-prep-query-sent"))


async def _handle_my_interviews(
    callback: CallbackQuery, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    from src.bot.modules.interviews.handlers import show_interview_list

    await show_interview_list(callback, user, i18n, session)


async def _handle_support(
    callback: CallbackQuery, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    from src.bot.modules.support.user_handlers import show_ticket_list

    await show_ticket_list(callback, user, session, i18n)


async def _handle_work_experience(
    callback: CallbackQuery, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    from src.bot.modules.work_experience.handlers import show_work_experience

    await show_work_experience(callback.message, user, "menu", session, i18n)


async def _handle_achievements(
    callback: CallbackQuery, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    from src.bot.modules.achievements.handlers import show_achievement_list

    await show_achievement_list(callback, user, session, i18n)


async def _handle_interview_qa(
    callback: CallbackQuery, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    from src.bot.modules.interview_qa.handlers import show_interview_qa_list

    await show_interview_qa_list(callback, user, session, i18n)


async def _handle_vacancy_summary(
    callback: CallbackQuery, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    from src.bot.modules.vacancy_summary.handlers import show_vacancy_summary_list

    await show_vacancy_summary_list(callback, user, session, i18n)


async def _handle_resume(
    callback: CallbackQuery, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    from src.bot.modules.resume.handlers import show_resume_list

    await show_resume_list(callback, user, session, i18n)


async def _handle_cover_letter(
    callback: CallbackQuery, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    from src.bot.modules.cover_letter.handlers import show_cover_letter_hub

    await show_cover_letter_hub(callback, i18n)


_MENU_DISPATCH = {
    "main": _handle_main,
    "profile": _handle_profile,
    "settings": _handle_settings,
    "my_parsings": _handle_my_parsings,
    "autoparse": _handle_autoparse,
    "admin": _handle_admin,
    "generate_vacancy_prep_query": _handle_generate_vacancy_prep_query,
    "my_interviews": _handle_my_interviews,
    "support": _handle_support,
    "work_experience": _handle_work_experience,
    "achievements": _handle_achievements,
    "interview_qa": _handle_interview_qa,
    "vacancy_summary": _handle_vacancy_summary,
    "resume": _handle_resume,
    "cover_letter": _handle_cover_letter,
}
