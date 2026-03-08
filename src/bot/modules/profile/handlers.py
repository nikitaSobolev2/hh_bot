from aiogram import Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.common import back_to_menu_keyboard
from src.bot.modules.profile import services as profile_service
from src.bot.modules.profile.callbacks import ProfileCallback
from src.bot.modules.profile.keyboards import profile_keyboard
from src.core.i18n import I18nContext
from src.models.user import User

router = Router(name="profile")


async def show_profile(callback: CallbackQuery, user: User, i18n: I18nContext) -> None:
    text = profile_service.format_profile(user, i18n)
    await callback.message.edit_text(text, reply_markup=profile_keyboard(i18n))


@router.callback_query(ProfileCallback.filter())
async def profile_actions(
    callback: CallbackQuery,
    callback_data: ProfileCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    action = callback_data.action

    if action == "stats":
        text = await profile_service.get_stats(session, user.id, i18n)
        await callback.message.edit_text(text, reply_markup=back_to_menu_keyboard(i18n))

    elif action == "referral":
        text = profile_service.format_referral_link(user, i18n)
        await callback.message.edit_text(text, reply_markup=back_to_menu_keyboard(i18n))

    await callback.answer()
