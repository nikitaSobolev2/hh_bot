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
from src.core.i18n import I18nContext
from src.models.user import User

router = Router(name="user_settings")


async def show_settings(callback: CallbackQuery, i18n: I18nContext) -> None:
    await callback.message.edit_text(
        f"{i18n.get('settings-title')}\n\n{i18n.get('settings-subtitle')}",
        reply_markup=settings_keyboard(i18n),
    )


@router.callback_query(SettingsCallback.filter())
async def settings_actions(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    action = callback_data.action

    if action == "language":
        await callback.message.edit_text(
            f"{i18n.get('language-title')}\n\n{i18n.get('language-subtitle')}",
            reply_markup=language_keyboard(i18n),
        )

    elif action == "set_lang":
        lang = callback_data.value
        await settings_service.set_language(session, user.id, lang)
        lang_name = "Русский" if lang == "ru" else "English"
        await callback.message.edit_text(
            i18n.get("language-set", language=lang_name),
            reply_markup=settings_keyboard(i18n),
        )

    elif action == "back":
        await show_settings(callback, i18n)

    elif action == "clear_blacklist":
        await _show_blacklist_management(callback, user, session, i18n)

    elif action == "notifications":
        await callback.message.edit_text(
            f"{i18n.get('notifications-title')}\n\n{i18n.get('notifications-soon')}",
            reply_markup=back_to_menu_keyboard(i18n),
        )

    elif action == "topup":
        await callback.message.edit_text(
            f"{i18n.get('topup-title')}\n\n{i18n.get('topup-soon')}",
            reply_markup=back_to_menu_keyboard(i18n),
        )

    elif action == "delete_data":
        await callback.message.edit_text(
            f"{i18n.get('delete-data-title')}\n\n{i18n.get('delete-data-warning')}",
            reply_markup=back_to_menu_keyboard(i18n),
        )

    await callback.answer()


async def _show_blacklist_management(
    callback: CallbackQuery, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    contexts = await settings_service.get_blacklist_contexts(session, user.id)

    if not contexts:
        await callback.message.edit_text(
            i18n.get("blacklist-empty"),
            reply_markup=settings_keyboard(i18n),
        )
        return

    text = settings_service.format_blacklist_text(contexts, i18n)
    await callback.message.edit_text(
        text, reply_markup=blacklist_management_keyboard(contexts, i18n)
    )


@router.callback_query(BlacklistCallback.filter())
async def blacklist_actions(
    callback: CallbackQuery,
    callback_data: BlacklistCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    action = callback_data.action

    if action == "clear_all":
        count = await settings_service.clear_all_blacklist(session, user.id)
        await callback.message.edit_text(
            i18n.get("blacklist-cleared", count=str(count)),
            reply_markup=settings_keyboard(i18n),
        )

    elif action == "clear_ctx":
        count = await settings_service.clear_blacklist_by_context(
            session, user.id, callback_data.context
        )
        await callback.message.edit_text(
            i18n.get("blacklist-cleared-ctx", count=str(count), context=callback_data.context),
            reply_markup=settings_keyboard(i18n),
        )

    await callback.answer()
