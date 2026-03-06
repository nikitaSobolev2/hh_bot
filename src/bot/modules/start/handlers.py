from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.callbacks.common import MenuCallback
from src.bot.keyboards.common import main_menu_admin_keyboard, main_menu_keyboard
from src.bot.modules.start.services import process_referral
from src.models.user import User

router = Router(name="start")

WELCOME_TEXT = (
    "<b>HH Bot</b> — your HeadHunter vacancy parser\n\n"
    "Analyze vacancies, extract keywords, and build better resumes."
)

_HANDLED_IN_START = {"main", "profile", "settings", "my_parsings", "admin"}


def _menu_keyboard(user: User) -> object:
    return main_menu_admin_keyboard() if user.is_admin else main_menu_keyboard()


@router.message(CommandStart(deep_link=True))
async def cmd_start_deep_link(message: Message, user: User, session: AsyncSession) -> None:
    args = message.text.split(maxsplit=1)
    deep_link = args[1] if len(args) > 1 else ""

    if deep_link.startswith("ref_"):
        await process_referral(session, user, deep_link[4:])

    await message.answer(WELCOME_TEXT, reply_markup=_menu_keyboard(user))


@router.message(CommandStart())
async def cmd_start(message: Message, user: User) -> None:
    await message.answer(WELCOME_TEXT, reply_markup=_menu_keyboard(user))


@router.callback_query(MenuCallback.filter(F.action.in_(_HANDLED_IN_START)))
async def menu_navigation(
    callback: CallbackQuery, callback_data: MenuCallback, user: User
) -> None:
    action = callback_data.action

    if action == "main":
        await callback.message.edit_text(WELCOME_TEXT, reply_markup=_menu_keyboard(user))

    elif action == "profile":
        from src.bot.modules.profile.handlers import show_profile

        await show_profile(callback, user)

    elif action == "settings":
        from src.bot.modules.user_settings.handlers import show_settings

        await show_settings(callback)

    elif action == "my_parsings":
        from src.bot.modules.parsing.handlers import show_parsing_list

        await show_parsing_list(callback, user)

    elif action == "admin":
        if not user.is_admin:
            await callback.answer("Access denied", show_alert=True)
            return
        from src.bot.modules.admin.handlers import show_admin_panel

        await show_admin_panel(callback)

    await callback.answer()
