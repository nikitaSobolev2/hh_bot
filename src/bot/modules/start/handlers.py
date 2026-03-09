from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.callbacks.common import MenuCallback
from src.bot.keyboards.common import main_menu_admin_keyboard, main_menu_keyboard
from src.bot.modules.start.services import process_referral
from src.core.i18n import I18nContext
from src.models.user import User

router = Router(name="start")

_HANDLED_IN_START = {"main", "profile", "settings", "my_parsings", "autoparse", "admin", "support"}


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
    action = callback_data.action

    if action == "main":
        await callback.message.edit_text(
            i18n.get("welcome"), reply_markup=_menu_keyboard(user, i18n)
        )

    elif action == "profile":
        from src.bot.modules.profile.handlers import show_profile

        await show_profile(callback, user, i18n)

    elif action == "settings":
        from src.bot.modules.user_settings.handlers import show_settings

        await show_settings(callback, i18n)

    elif action == "my_parsings":
        from src.bot.modules.parsing.handlers import show_parsing_list

        await show_parsing_list(callback, user, i18n)

    elif action == "autoparse":
        from src.bot.modules.autoparse.handlers import show_autoparse_hub

        await show_autoparse_hub(callback, i18n)

    elif action == "admin":
        if not user.is_admin:
            await callback.answer(i18n.get("access-denied"), show_alert=True)
            return
        from src.bot.modules.admin.handlers import show_admin_panel

        await show_admin_panel(callback, i18n)

    elif action == "support":
        from src.bot.modules.support.user_handlers import show_ticket_list

        await show_ticket_list(callback, user, session, i18n)

    await callback.answer()
