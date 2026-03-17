from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.filters.admin import AdminFilter
from src.bot.keyboards.common import back_to_menu_keyboard
from src.bot.modules.admin import services as admin_service
from src.bot.modules.admin.callbacks import AdminCallback, AdminSettingCallback, AdminUserCallback
from src.bot.modules.admin.keyboards import (
    AUTOPARSE_TARGET_VALID,
    admin_menu_keyboard,
    back_to_settings_keyboard,
    setting_detail_keyboard,
    settings_list_keyboard,
    user_detail_keyboard,
    user_list_keyboard,
)
from src.bot.modules.admin.states import (
    AdminBalanceForm,
    AdminMessageForm,
    AdminSettingForm,
    AdminUserSearchForm,
)
from src.core.i18n import I18nContext
from src.models.user import User

router = Router(name="admin")
router.callback_query.filter(AdminFilter())
router.message.filter(AdminFilter())


async def show_admin_panel(callback: CallbackQuery, i18n: I18nContext) -> None:
    await callback.message.edit_text(
        f"{i18n.get('admin-title')}\n\n{i18n.get('admin-subtitle')}",
        reply_markup=admin_menu_keyboard(i18n),
    )


# --------------- panel actions ---------------


@router.callback_query(AdminCallback.filter())
async def admin_panel_actions(
    callback: CallbackQuery,
    callback_data: AdminCallback,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    action = callback_data.action

    if action == "users":
        await _show_user_list(callback, session, i18n)
    elif action == "settings":
        await callback.message.edit_text(
            i18n.get("admin-setting-select"),
            reply_markup=settings_list_keyboard(i18n),
        )
    elif action == "support":
        from src.bot.modules.support.admin_handlers import show_admin_inbox

        await show_admin_inbox(callback, session, i18n)
    elif action == "back":
        await show_admin_panel(callback, i18n)

    await callback.answer()


# --------------- user management ---------------


async def _show_user_list(
    callback: CallbackQuery, session: AsyncSession, i18n: I18nContext, page: int = 0
) -> None:
    users, has_more = await admin_service.get_user_page(session, page)

    if not users:
        await callback.message.edit_text(
            i18n.get("admin-users-empty"),
            reply_markup=back_to_menu_keyboard(i18n),
        )
        return

    await callback.message.edit_text(
        i18n.get("admin-users-page", page=str(page + 1)),
        reply_markup=user_list_keyboard(users, page, has_more, i18n),
    )


@router.callback_query(AdminUserCallback.filter(F.action == "list"))
async def user_list_page(
    callback: CallbackQuery,
    callback_data: AdminUserCallback,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await _show_user_list(callback, session, i18n, callback_data.page)
    await callback.answer()


@router.callback_query(AdminUserCallback.filter(F.action == "search"))
async def user_search_prompt(callback: CallbackQuery, state: FSMContext, i18n: I18nContext) -> None:
    await callback.message.edit_text(
        i18n.get("admin-search-prompt"),
        reply_markup=back_to_menu_keyboard(i18n),
    )
    await state.set_state(AdminUserSearchForm.waiting_query)
    await callback.answer()


@router.callback_query(AdminUserCallback.filter(F.action == "detail"))
async def user_detail(
    callback: CallbackQuery,
    callback_data: AdminUserCallback,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    target = await admin_service.get_user_by_id(session, callback_data.user_id)
    if not target:
        await callback.answer(i18n.get("admin-user-not-found"), show_alert=True)
        return
    text = admin_service.format_user_detail(target, i18n)
    await callback.message.edit_text(text, reply_markup=user_detail_keyboard(target, i18n))
    await callback.answer()


@router.callback_query(AdminUserCallback.filter(F.action == "toggle_ban"))
async def user_toggle_ban(
    callback: CallbackQuery,
    callback_data: AdminUserCallback,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    target = await admin_service.toggle_user_ban(session, callback_data.user_id)
    if target:
        status_key = "admin-user-banned" if target.is_banned else "admin-user-unbanned"
        await callback.answer(i18n.get(status_key), show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=user_detail_keyboard(target, i18n))
    else:
        await callback.answer()


@router.callback_query(AdminUserCallback.filter(F.action == "balance"))
async def user_balance_prompt(
    callback: CallbackQuery,
    callback_data: AdminUserCallback,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.update_data(target_user_id=callback_data.user_id)
    await state.set_state(AdminBalanceForm.waiting_amount)
    await callback.message.edit_text(
        i18n.get("admin-balance-prompt"),
        reply_markup=back_to_menu_keyboard(i18n),
    )
    await callback.answer()


@router.callback_query(AdminUserCallback.filter(F.action == "message"))
async def user_message_prompt(
    callback: CallbackQuery,
    callback_data: AdminUserCallback,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.update_data(target_user_id=callback_data.user_id)
    await state.set_state(AdminMessageForm.waiting_message)
    await callback.message.edit_text(
        i18n.get("admin-send-message-prompt"),
        reply_markup=back_to_menu_keyboard(i18n),
    )
    await callback.answer()


@router.message(AdminUserSearchForm.waiting_query)
async def handle_user_search(
    message: Message, user: User, state: FSMContext, session: AsyncSession, i18n: I18nContext
) -> None:
    query = message.text.strip()
    await state.clear()

    users = await admin_service.search_users(session, query)
    if not users:
        await message.answer(
            i18n.get("admin-search-empty", query=query),
            reply_markup=back_to_menu_keyboard(i18n),
        )
        return

    await message.answer(
        i18n.get("admin-search-results", query=query),
        reply_markup=user_list_keyboard(users, 0, False, i18n),
    )


@router.message(AdminBalanceForm.waiting_amount)
async def handle_balance_adjust(
    message: Message, user: User, state: FSMContext, session: AsyncSession, i18n: I18nContext
) -> None:
    from decimal import Decimal, InvalidOperation

    data = await state.get_data()
    await state.clear()

    try:
        amount = Decimal(message.text.strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        await message.answer(
            i18n.get("admin-invalid-amount"), reply_markup=back_to_menu_keyboard(i18n)
        )
        return

    target_user_id = data.get("target_user_id")
    locale = user.language_code or "ru"
    target = await admin_service.adjust_balance(
        session, target_user_id, amount, user.id, locale=locale
    )
    if not target:
        await message.answer(
            i18n.get("admin-user-not-found-short"), reply_markup=back_to_menu_keyboard(i18n)
        )
        return

    await message.answer(
        i18n.get("admin-balance-adjusted", amount=str(amount), user_id=str(target_user_id)),
        reply_markup=back_to_menu_keyboard(i18n),
    )


@router.message(AdminMessageForm.waiting_message)
async def handle_send_message(
    message: Message, user: User, state: FSMContext, session: AsyncSession, i18n: I18nContext
) -> None:
    data = await state.get_data()
    await state.clear()

    target_user_id = data.get("target_user_id")
    text = message.text.strip()

    target = await admin_service.get_user_by_id(session, target_user_id)
    if not target:
        await message.answer(
            i18n.get("admin-user-not-found-short"), reply_markup=back_to_menu_keyboard(i18n)
        )
        return

    try:
        await message.bot.send_message(
            target.telegram_id,
            f"{i18n.get('admin-message-from-admin')}\n\n{text}",
        )
        await message.answer(
            i18n.get("admin-message-sent"), reply_markup=back_to_menu_keyboard(i18n)
        )
    except Exception:
        await message.answer(
            i18n.get("admin-message-failed"), reply_markup=back_to_menu_keyboard(i18n)
        )


# --------------- app settings ---------------


@router.callback_query(AdminSettingCallback.filter())
async def admin_setting_actions(
    callback: CallbackQuery,
    callback_data: AdminSettingCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    action = callback_data.action
    locale = user.language_code or "ru"

    if action == "list":
        await callback.message.edit_text(
            i18n.get("admin-setting-select"),
            reply_markup=settings_list_keyboard(i18n),
        )

    elif action == "view":
        meta = admin_service.find_setting_meta(callback_data.key)
        if not meta:
            await callback.answer(i18n.get("admin-setting-unknown"), show_alert=True)
            return

        key, label, stype, choices = meta[0], meta[1], meta[2], meta[3]
        current = await admin_service.get_setting_value(session, key, locale=locale)
        display = admin_service.mask_if_sensitive(key, str(current))
        await callback.message.edit_text(
            i18n.get("admin-setting-current", label=label, value=display),
            reply_markup=setting_detail_keyboard(key, stype, i18n, choices=choices),
        )

    elif action == "select_value":
        key = callback_data.key
        if key != "autoparse_target_count":
            await callback.answer(i18n.get("admin-setting-unknown"), show_alert=True)
            return
        try:
            val = int(callback_data.value)
        except ValueError:
            await callback.answer(i18n.get("admin-setting-unknown"), show_alert=True)
            return
        if val not in AUTOPARSE_TARGET_VALID:
            await callback.answer(i18n.get("admin-setting-unknown"), show_alert=True)
            return
        await admin_service.update_setting(session, key, str(val), user.id)
        msg = i18n.get("admin-setting-set", value=callback_data.value)
        await callback.answer(msg, show_alert=True)
        meta = admin_service.find_setting_meta(key)
        if meta:
            current = await admin_service.get_setting_value(session, key, locale=locale)
            display = str(current)
            await callback.message.edit_text(
                i18n.get("admin-setting-current", label=meta[1], value=display),
                reply_markup=setting_detail_keyboard(
                    meta[0], meta[2], i18n, choices=meta[3]
                ),
            )
        return

    elif action == "toggle":
        new_val = await admin_service.toggle_setting(session, callback_data.key, user.id)
        await callback.answer(i18n.get("admin-setting-set", value=str(new_val)), show_alert=True)

        meta = admin_service.find_setting_meta(callback_data.key)
        if meta:
            await callback.message.edit_text(
                i18n.get("admin-setting-current", label=meta[1], value=str(new_val)),
                reply_markup=setting_detail_keyboard(
                    meta[0], meta[2], i18n, choices=meta[3]
                ),
            )
        return

    elif action == "edit":
        meta = admin_service.find_setting_meta(callback_data.key)
        if meta and meta[2] == "select":
            await callback.answer(i18n.get("admin-setting-select-use-buttons"), show_alert=True)
            return
        await state.update_data(setting_key=callback_data.key)
        await state.set_state(AdminSettingForm.waiting_value)
        meta = admin_service.find_setting_meta(callback_data.key)
        label = meta[1] if meta else callback_data.key
        await callback.message.edit_text(
            i18n.get("admin-setting-edit", label=label),
            reply_markup=back_to_settings_keyboard(i18n),
        )

    await callback.answer()


@router.message(AdminSettingForm.waiting_value)
async def handle_setting_value(
    message: Message, user: User, state: FSMContext, session: AsyncSession, i18n: I18nContext
) -> None:
    data = await state.get_data()
    await state.clear()
    key = data.get("setting_key", "")

    await admin_service.update_setting(session, key, message.text.strip(), user.id)

    meta = admin_service.find_setting_meta(key)
    label = meta[1] if meta else key
    await message.answer(
        i18n.get("admin-setting-updated", label=label),
        reply_markup=back_to_settings_keyboard(i18n),
    )
