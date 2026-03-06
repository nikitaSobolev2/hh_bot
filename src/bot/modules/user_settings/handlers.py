from aiogram import Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.common import back_to_menu_keyboard
from src.bot.modules.user_settings import services as settings_service
from src.bot.modules.user_settings.callbacks import BlacklistCallback, SettingsCallback
from src.bot.modules.user_settings.keyboards import (
    blacklist_management_keyboard,
    language_keyboard,
    settings_keyboard,
)
from src.models.user import User

router = Router(name="user_settings")


async def show_settings(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "<b>⚙️ Settings</b>\n\nManage your preferences.",
        reply_markup=settings_keyboard(),
    )


@router.callback_query(SettingsCallback.filter())
async def settings_actions(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    user: User,
    session: AsyncSession,
) -> None:
    action = callback_data.action

    if action == "language":
        await callback.message.edit_text(
            "<b>🌐 Language</b>\n\nSelect your language:",
            reply_markup=language_keyboard(),
        )

    elif action == "set_lang":
        lang = callback_data.value
        await settings_service.set_language(session, user.id, lang)
        await callback.message.edit_text(
            f"Language set to <b>{'Русский' if lang == 'ru' else 'English'}</b>",
            reply_markup=settings_keyboard(),
        )

    elif action == "back":
        await show_settings(callback)

    elif action == "clear_blacklist":
        await _show_blacklist_management(callback, user, session)

    elif action == "notifications":
        await callback.message.edit_text(
            "<b>🔔 Notifications</b>\n\nComing soon.",
            reply_markup=back_to_menu_keyboard(),
        )

    elif action == "topup":
        await callback.message.edit_text(
            "<b>💰 Top Up Balance</b>\n\nPayment methods coming soon.",
            reply_markup=back_to_menu_keyboard(),
        )

    elif action == "delete_data":
        await callback.message.edit_text(
            "<b>⚠️ Delete My Data</b>\n\n"
            "This feature will permanently delete all your data. "
            "Implementation details to be confirmed.",
            reply_markup=back_to_menu_keyboard(),
        )

    await callback.answer()


async def _show_blacklist_management(
    callback: CallbackQuery, user: User, session: AsyncSession
) -> None:
    contexts = await settings_service.get_blacklist_contexts(session, user.id)

    if not contexts:
        await callback.message.edit_text(
            "<b>🗑 Blacklist</b>\n\nNo active blacklist entries.",
            reply_markup=settings_keyboard(),
        )
        return

    text = settings_service.format_blacklist_text(contexts)
    await callback.message.edit_text(
        text, reply_markup=blacklist_management_keyboard(contexts)
    )


@router.callback_query(BlacklistCallback.filter())
async def blacklist_actions(
    callback: CallbackQuery,
    callback_data: BlacklistCallback,
    user: User,
    session: AsyncSession,
) -> None:
    action = callback_data.action

    if action == "clear_all":
        count = await settings_service.clear_all_blacklist(session, user.id)
        await callback.message.edit_text(
            f"Cleared <b>{count}</b> blacklist entries.",
            reply_markup=settings_keyboard(),
        )

    elif action == "clear_ctx":
        count = await settings_service.clear_blacklist_by_context(
            session, user.id, callback_data.context
        )
        await callback.message.edit_text(
            f"Cleared <b>{count}</b> entries for <b>{callback_data.context}</b>.",
            reply_markup=settings_keyboard(),
        )

    await callback.answer()
