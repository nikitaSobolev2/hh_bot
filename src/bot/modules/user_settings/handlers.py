import contextlib

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.common import back_to_menu_keyboard
from src.bot.modules.user_settings import services as settings_service
from src.bot.modules.user_settings.callbacks import (
    BlacklistCallback,
    SettingsCallback,
    TimezoneCallback,
)
from src.bot.modules.user_settings.keyboards import (
    POPULAR_TIMEZONES,
    blacklist_management_keyboard,
    language_keyboard,
    settings_keyboard,
    timezone_keyboard,
)
from src.bot.modules.user_settings.states import UserSettingsForm
from src.core.i18n import I18nContext
from src.models.user import User

router = Router(name="user_settings")


async def _safe_edit_text(
    callback: CallbackQuery,
    text: str,
    **kwargs,
) -> None:
    from aiogram.exceptions import TelegramBadRequest

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, **kwargs)


async def show_settings(callback: CallbackQuery, i18n: I18nContext) -> None:
    await _safe_edit_text(
        callback,
        f"{i18n.get('settings-title')}\n\n{i18n.get('settings-subtitle')}",
        reply_markup=settings_keyboard(i18n),
    )


@router.callback_query(SettingsCallback.filter())
async def settings_actions(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    user: User,
    session: AsyncSession,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    action = callback_data.action

    if action == "language":
        await _safe_edit_text(
            callback,
            f"{i18n.get('language-title')}\n\n{i18n.get('language-subtitle')}",
            reply_markup=language_keyboard(i18n),
        )

    elif action == "set_lang":
        lang = callback_data.value
        await settings_service.set_language(session, user.id, lang)
        lang_name = "Русский" if lang == "ru" else "English"
        await _safe_edit_text(
            callback,
            i18n.get("language-set", language=lang_name),
            reply_markup=settings_keyboard(i18n),
        )

    elif action == "back":
        await show_settings(callback, i18n)

    elif action == "clear_blacklist":
        await _show_blacklist_management(callback, user, session, i18n)

    elif action == "notifications":
        await _safe_edit_text(
            callback,
            f"{i18n.get('notifications-title')}\n\n{i18n.get('notifications-soon')}",
            reply_markup=back_to_menu_keyboard(i18n),
        )

    elif action == "topup":
        await _safe_edit_text(
            callback,
            f"{i18n.get('topup-title')}\n\n{i18n.get('topup-soon')}",
            reply_markup=back_to_menu_keyboard(i18n),
        )

    elif action == "timezone":
        await _safe_edit_text(
            callback,
            i18n.get("settings-timezone-current", tz=user.timezone)
            + "\n\n"
            + i18n.get("settings-timezone-select"),
            reply_markup=timezone_keyboard(0, i18n),
        )

    elif action == "delete_data":
        await _safe_edit_text(
            callback,
            f"{i18n.get('delete-data-title')}\n\n{i18n.get('delete-data-warning')}",
            reply_markup=back_to_menu_keyboard(i18n),
        )

    await callback.answer()


# ── Timezone picker ──────────────────────────────────────────────────


@router.callback_query(TimezoneCallback.filter())
async def timezone_actions(
    callback: CallbackQuery,
    callback_data: TimezoneCallback,
    user: User,
    session: AsyncSession,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    action = callback_data.action

    if action == "page":
        fsm_data = await state.get_data()
        search_q = fsm_data.get("tz_search_query")
        await _safe_edit_text(
            callback,
            i18n.get("settings-timezone-current", tz=user.timezone)
            + "\n\n"
            + i18n.get("settings-timezone-select"),
            reply_markup=timezone_keyboard(callback_data.page, i18n, search_query=search_q),
        )

    elif action == "select":
        tz = callback_data.value
        await settings_service.set_timezone(session, user.id, tz)
        await state.clear()
        await _safe_edit_text(
            callback,
            i18n.get("settings-timezone-set", tz=tz),
            reply_markup=settings_keyboard(i18n),
        )

    elif action == "search":
        await state.set_state(UserSettingsForm.timezone_search)
        await _safe_edit_text(
            callback,
            i18n.get("settings-timezone-search"),
            reply_markup=settings_keyboard(i18n),
        )

    await callback.answer()


@router.message(UserSettingsForm.timezone_search)
async def receive_timezone_search(
    message: Message,
    state: FSMContext,
    user: User,
    i18n: I18nContext,
) -> None:
    query = message.text.strip()
    await state.clear()
    await state.update_data(tz_search_query=query)

    q = query.lower()
    has_matches = any(q in tz.lower() or q in off.lower() for tz, off in POPULAR_TIMEZONES)
    if not has_matches:
        await message.answer(
            i18n.get("settings-timezone-no-results"),
            reply_markup=timezone_keyboard(0, i18n),
        )
        return

    await message.answer(
        i18n.get("settings-timezone-current", tz=user.timezone)
        + "\n\n"
        + i18n.get("settings-timezone-select"),
        reply_markup=timezone_keyboard(0, i18n, search_query=query),
    )


# ── Blacklist ────────────────────────────────────────────────────────


async def _show_blacklist_management(
    callback: CallbackQuery, user: User, session: AsyncSession, i18n: I18nContext
) -> None:
    contexts = await settings_service.get_blacklist_contexts(session, user.id)

    if not contexts:
        await _safe_edit_text(
            callback,
            i18n.get("blacklist-empty"),
            reply_markup=settings_keyboard(i18n),
        )
        return

    text = settings_service.format_blacklist_text(contexts, i18n)
    await _safe_edit_text(
        callback, text, reply_markup=blacklist_management_keyboard(contexts, i18n)
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
        await _safe_edit_text(
            callback,
            i18n.get("blacklist-cleared", count=str(count)),
            reply_markup=settings_keyboard(i18n),
        )

    elif action == "clear_ctx":
        count = await settings_service.clear_blacklist_by_context(
            session, user.id, callback_data.context
        )
        await _safe_edit_text(
            callback,
            i18n.get("blacklist-cleared-ctx", count=str(count), context=callback_data.context),
            reply_markup=settings_keyboard(i18n),
        )

    await callback.answer()
