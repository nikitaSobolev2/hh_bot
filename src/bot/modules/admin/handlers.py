from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.filters.admin import AdminFilter
from src.bot.keyboards.common import back_to_menu_keyboard
from src.bot.modules.admin import services as admin_service
from src.bot.modules.admin.callbacks import AdminCallback, AdminSettingCallback, AdminUserCallback
from src.bot.modules.admin.keyboards import (
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
from src.models.user import User

router = Router(name="admin")
router.callback_query.filter(AdminFilter())
router.message.filter(AdminFilter())


async def show_admin_panel(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "<b>🛠 Admin Panel</b>\n\nManage users, settings, and tasks.",
        reply_markup=admin_menu_keyboard(),
    )


# --------------- panel actions ---------------


@router.callback_query(AdminCallback.filter())
async def admin_panel_actions(
    callback: CallbackQuery, callback_data: AdminCallback, session: AsyncSession
) -> None:
    action = callback_data.action

    if action == "users":
        await _show_user_list(callback, session)
    elif action == "settings":
        await callback.message.edit_text(
            "<b>⚙️ App Settings</b>\n\nSelect a setting to view or edit:",
            reply_markup=settings_list_keyboard(),
        )
    elif action == "support":
        await callback.message.edit_text(
            "<b>📬 Support Inbox</b>\n\nNo messages yet.\n\n"
            "Users can send support messages which will appear here.",
            reply_markup=back_to_menu_keyboard(),
        )
    elif action == "back":
        await show_admin_panel(callback)

    await callback.answer()


# --------------- user management ---------------


async def _show_user_list(
    callback: CallbackQuery, session: AsyncSession, page: int = 0
) -> None:
    users, has_more = await admin_service.get_user_page(session, page)

    if not users:
        await callback.message.edit_text(
            "<b>👥 Users</b>\n\nNo users found.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    await callback.message.edit_text(
        f"<b>👥 Users</b> (page {page + 1})",
        reply_markup=user_list_keyboard(users, page, has_more),
    )


@router.callback_query(AdminUserCallback.filter(F.action == "list"))
async def user_list_page(
    callback: CallbackQuery, callback_data: AdminUserCallback, session: AsyncSession
) -> None:
    await _show_user_list(callback, session, callback_data.page)
    await callback.answer()


@router.callback_query(AdminUserCallback.filter(F.action == "search"))
async def user_search_prompt(
    callback: CallbackQuery, state: FSMContext
) -> None:
    await callback.message.edit_text(
        "<b>🔍 Search Users</b>\n\nEnter username, name, or Telegram ID:",
        reply_markup=back_to_menu_keyboard(),
    )
    await state.set_state(AdminUserSearchForm.waiting_query)
    await callback.answer()


@router.callback_query(AdminUserCallback.filter(F.action == "detail"))
async def user_detail(
    callback: CallbackQuery, callback_data: AdminUserCallback, session: AsyncSession
) -> None:
    target = await admin_service.get_user_by_id(session, callback_data.user_id)
    if not target:
        await callback.answer("User not found", show_alert=True)
        return
    text = admin_service.format_user_detail(target)
    await callback.message.edit_text(text, reply_markup=user_detail_keyboard(target))
    await callback.answer()


@router.callback_query(AdminUserCallback.filter(F.action == "toggle_ban"))
async def user_toggle_ban(
    callback: CallbackQuery, callback_data: AdminUserCallback, session: AsyncSession
) -> None:
    target = await admin_service.toggle_user_ban(session, callback_data.user_id)
    if target:
        status = "banned" if target.is_banned else "unbanned"
        await callback.answer(f"User {status}", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=user_detail_keyboard(target))
    else:
        await callback.answer()


@router.callback_query(AdminUserCallback.filter(F.action == "balance"))
async def user_balance_prompt(
    callback: CallbackQuery, callback_data: AdminUserCallback, state: FSMContext
) -> None:
    await state.update_data(target_user_id=callback_data.user_id)
    await state.set_state(AdminBalanceForm.waiting_amount)
    await callback.message.edit_text(
        "<b>💰 Adjust Balance</b>\n\nEnter amount (positive to add, negative to deduct):",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(AdminUserCallback.filter(F.action == "message"))
async def user_message_prompt(
    callback: CallbackQuery, callback_data: AdminUserCallback, state: FSMContext
) -> None:
    await state.update_data(target_user_id=callback_data.user_id)
    await state.set_state(AdminMessageForm.waiting_message)
    await callback.message.edit_text(
        "<b>✉️ Send Message</b>\n\nType the message to send to this user:",
        reply_markup=back_to_menu_keyboard(),
    )
    await callback.answer()


@router.message(AdminUserSearchForm.waiting_query)
async def handle_user_search(
    message: Message, user: User, state: FSMContext, session: AsyncSession
) -> None:
    query = message.text.strip()
    await state.clear()

    users = await admin_service.search_users(session, query)
    if not users:
        await message.answer(
            f"No users found for <b>{query}</b>",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    await message.answer(
        f"<b>🔍 Results for «{query}»</b>",
        reply_markup=user_list_keyboard(users, 0, False),
    )


@router.message(AdminBalanceForm.waiting_amount)
async def handle_balance_adjust(
    message: Message, user: User, state: FSMContext, session: AsyncSession
) -> None:
    from decimal import Decimal, InvalidOperation

    data = await state.get_data()
    await state.clear()

    try:
        amount = Decimal(message.text.strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        await message.answer(
            "Invalid amount. Enter a number.", reply_markup=back_to_menu_keyboard()
        )
        return

    target_user_id = data.get("target_user_id")
    target = await admin_service.adjust_balance(session, target_user_id, amount, user.id)
    if not target:
        await message.answer("User not found.", reply_markup=back_to_menu_keyboard())
        return

    await message.answer(
        f"Balance adjusted by <b>{amount}</b> for user #{target_user_id}.",
        reply_markup=back_to_menu_keyboard(),
    )


@router.message(AdminMessageForm.waiting_message)
async def handle_send_message(
    message: Message, user: User, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    await state.clear()

    target_user_id = data.get("target_user_id")
    text = message.text.strip()

    target = await admin_service.get_user_by_id(session, target_user_id)
    if not target:
        await message.answer("User not found.", reply_markup=back_to_menu_keyboard())
        return

    try:
        await message.bot.send_message(
            target.telegram_id,
            f"<b>📢 Message from Admin</b>\n\n{text}",
        )
        await message.answer("Message sent.", reply_markup=back_to_menu_keyboard())
    except Exception:
        await message.answer("Failed to send message.", reply_markup=back_to_menu_keyboard())


# --------------- app settings ---------------


@router.callback_query(AdminSettingCallback.filter())
async def admin_setting_actions(
    callback: CallbackQuery,
    callback_data: AdminSettingCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    action = callback_data.action

    if action == "list":
        await callback.message.edit_text(
            "<b>⚙️ App Settings</b>\n\nSelect a setting to view or edit:",
            reply_markup=settings_list_keyboard(),
        )

    elif action == "view":
        meta = admin_service.find_setting_meta(callback_data.key)
        if not meta:
            await callback.answer("Unknown setting", show_alert=True)
            return

        key, label, stype = meta
        current = await admin_service.get_setting_value(session, key)
        display = admin_service.mask_if_sensitive(key, str(current))
        await callback.message.edit_text(
            f"<b>⚙️ {label}</b>\n\nCurrent value: <code>{display}</code>",
            reply_markup=setting_detail_keyboard(key, stype),
        )

    elif action == "toggle":
        new_val = await admin_service.toggle_setting(session, callback_data.key, user.id)
        await callback.answer(f"Set to {new_val}", show_alert=True)

        meta = admin_service.find_setting_meta(callback_data.key)
        if meta:
            await callback.message.edit_text(
                f"<b>⚙️ {meta[1]}</b>\n\nCurrent value: <code>{new_val}</code>",
                reply_markup=setting_detail_keyboard(meta[0], meta[2]),
            )
        return

    elif action == "edit":
        await state.update_data(setting_key=callback_data.key)
        await state.set_state(AdminSettingForm.waiting_value)
        meta = admin_service.find_setting_meta(callback_data.key)
        label = meta[1] if meta else callback_data.key
        await callback.message.edit_text(
            f"<b>✏️ Edit {label}</b>\n\nEnter new value:",
            reply_markup=back_to_settings_keyboard(),
        )

    await callback.answer()


@router.message(AdminSettingForm.waiting_value)
async def handle_setting_value(
    message: Message, user: User, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    await state.clear()
    key = data.get("setting_key", "")

    await admin_service.update_setting(session, key, message.text.strip(), user.id)

    meta = admin_service.find_setting_meta(key)
    label = meta[1] if meta else key
    await message.answer(
        f"<b>⚙️ {label}</b> updated.",
        reply_markup=back_to_settings_keyboard(),
    )


