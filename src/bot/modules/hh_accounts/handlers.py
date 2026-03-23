"""Telegram UI for linking and managing HeadHunter accounts (OAuth or Playwright storage_state)."""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime
from io import BytesIO

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.modules.hh_accounts.callbacks import HhAccountCallback
from src.bot.modules.hh_accounts.keyboards import hh_account_row_keyboard, hh_accounts_hub_keyboard
from src.bot.modules.hh_accounts.states import HhAccountRenameForm, HhBrowserImportForm
from src.bot.modules.user_settings.callbacks import SettingsCallback
from src.config import settings
from src.core.i18n import I18nContext
from src.models.user import User
from src.repositories.hh_linked_account import HhLinkedAccountRepository
from src.services.hh.crypto import HhTokenCipher
from src.services.hh.oauth_state import generate_state, store_state
from src.services.hh.oauth_tokens import build_authorize_url
from src.services.hh_ui.browser_link import (
    encrypt_storage_for_account,
    make_hh_user_id_for_browser_link,
    placeholder_access_expires_at,
    placeholder_token_ciphertexts,
    validate_playwright_storage_state,
)

router = Router(name="hh_accounts")

_VALIDATION_ERROR_I18N = {
    "not-a-json-object": "hh-accounts-browser-err-not-object",
    "missing-cookies-array": "hh-accounts-browser-err-no-cookies",
    "no-hh-cookies": "hh-accounts-browser-err-no-hh",
}


def _utc_naive_now():
    return datetime.now(UTC).replace(tzinfo=None)


def _oauth_configured() -> bool:
    return bool(
        settings.hh_client_id
        and settings.hh_oauth_redirect_uri
        and settings.hh_token_encryption_key
    )


def _browser_import_configured() -> bool:
    return bool(settings.hh_ui_apply_enabled and settings.hh_token_encryption_key)


async def _hub_message(
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> tuple[str, InlineKeyboardMarkup]:
    repo = HhLinkedAccountRepository(session)
    accounts = await repo.list_active_for_user(user.id)
    if not accounts:
        return i18n.get("hh-accounts-empty"), hh_accounts_hub_keyboard(i18n)
    lines = [i18n.get("hh-accounts-title"), ""]
    for acc in accounts:
        label = acc.label or acc.hh_user_id
        lines.append(f"• {label}")
    text = "\n".join(lines)
    kb = hh_account_row_keyboard(accounts, i18n)
    return text, kb


async def _show_hub(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    text, kb = await _hub_message(session, user, i18n)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=kb)


@router.callback_query(HhAccountCallback.filter(F.action == "menu"))
async def open_hh_accounts_menu(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    await _show_hub(callback, session, user, i18n)
    await callback.answer()


@router.callback_query(HhAccountCallback.filter(F.action == "add"))
async def hh_add_account(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
    state: FSMContext,
) -> None:
    if _oauth_configured():
        st = generate_state()
        await store_state(st, user.telegram_id)
        url = build_authorize_url(state=st)
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=i18n.get("hh-accounts-open-browser"), url=url)],
                [
                    InlineKeyboardButton(
                        text=i18n.get("btn-back"),
                        callback_data=HhAccountCallback(action="menu").pack(),
                    )
                ],
            ]
        )
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("hh-accounts-add-hint"),
                reply_markup=kb,
            )
        await callback.answer()
        return

    if _browser_import_configured():
        await state.set_state(HhBrowserImportForm.waiting_json)
        cancel_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=i18n.get("btn-cancel"),
                        callback_data=HhAccountCallback(action="cancel_browser").pack(),
                    )
                ]
            ]
        )
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("hh-accounts-browser-import-hint"),
                reply_markup=cancel_kb,
                parse_mode="HTML",
            )
        await callback.answer()
        return

    await callback.answer(i18n.get("hh-link-not-available"), show_alert=True)


@router.callback_query(HhAccountCallback.filter(F.action == "cancel_browser"))
async def hh_cancel_browser_import(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.clear()
    await _show_hub(callback, session, user, i18n)
    await callback.answer()


@router.message(HhBrowserImportForm.waiting_json, F.document)
async def hh_browser_import_document(
    message: Message,
    session: AsyncSession,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    doc = message.document
    if not doc:
        return
    name = (doc.file_name or "").lower()
    if not name.endswith(".json"):
        await message.answer(i18n.get("hh-accounts-browser-import-bad-file"))
        return

    buf = BytesIO()
    await message.bot.download(doc, destination=buf)
    buf.seek(0)
    try:
        raw = buf.read().decode("utf-8")
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        await message.answer(i18n.get("hh-accounts-browser-import-bad-file"))
        return

    try:
        state_dict = validate_playwright_storage_state(parsed)
    except ValueError as exc:
        code = str(exc.args[0]) if exc.args else "unknown"
        msg_key = _VALIDATION_ERROR_I18N.get(code, "hh-accounts-browser-err-unknown")
        await message.answer(i18n.get(msg_key))
        return

    hh_uid = make_hh_user_id_for_browser_link(state_dict)
    cipher = HhTokenCipher(settings.hh_token_encryption_key)
    enc_storage = encrypt_storage_for_account(state_dict, cipher)
    now = _utc_naive_now()

    repo = HhLinkedAccountRepository(session)
    existing = await repo.get_by_user_and_hh_user_id(user.id, hh_uid)
    if existing:
        await repo.update(
            existing,
            browser_storage_enc=enc_storage,
            browser_storage_updated_at=now,
            revoked_at=None,
            last_used_at=now,
        )
    else:
        ph_access, ph_refresh = placeholder_token_ciphertexts(cipher)
        await repo.create(
            user_id=user.id,
            hh_user_id=hh_uid,
            label=None,
            access_token_enc=ph_access,
            refresh_token_enc=ph_refresh,
            access_expires_at=placeholder_access_expires_at(),
            revoked_at=None,
            last_used_at=now,
            browser_storage_enc=enc_storage,
            browser_storage_updated_at=now,
        )
    await session.commit()
    await state.clear()

    text, kb = await _hub_message(session, user, i18n)
    await message.answer(i18n.get("hh-accounts-browser-import-success"))
    await message.answer(text, reply_markup=kb)


@router.message(HhBrowserImportForm.waiting_json)
async def hh_browser_import_reminder(message: Message, i18n: I18nContext) -> None:
    await message.answer(i18n.get("hh-accounts-browser-import-send-file"))


@router.callback_query(HhAccountCallback.filter(F.action == "remove"))
async def hh_remove_account(
    callback: CallbackQuery,
    callback_data: HhAccountCallback,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    repo = HhLinkedAccountRepository(session)
    acc = await repo.get_by_id(callback_data.account_id)
    if not acc or acc.user_id != user.id:
        await callback.answer(i18n.get("hh-account-not-found"), show_alert=True)
        return
    await repo.update(acc, revoked_at=_utc_naive_now())
    await session.commit()
    await _show_hub(callback, session, user, i18n)
    await callback.answer(i18n.get("hh-accounts-removed"))


@router.callback_query(HhAccountCallback.filter(F.action == "rename"))
async def hh_rename_start(
    callback: CallbackQuery,
    callback_data: HhAccountCallback,
    session: AsyncSession,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    repo = HhLinkedAccountRepository(session)
    acc = await repo.get_by_id(callback_data.account_id)
    if not acc or acc.user_id != user.id:
        await callback.answer(i18n.get("hh-account-not-found"), show_alert=True)
        return
    await state.set_state(HhAccountRenameForm.waiting_label)
    await state.update_data(hh_account_id=acc.id)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=HhAccountCallback(action="cancel_rename").pack(),
                )
            ]
        ]
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("hh-accounts-rename-prompt"),
            reply_markup=kb,
        )
    await callback.answer()


@router.callback_query(HhAccountCallback.filter(F.action == "cancel_rename"))
async def hh_rename_cancel(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.clear()
    await _show_hub(callback, session, user, i18n)
    await callback.answer()


@router.message(HhAccountRenameForm.waiting_label)
async def hh_rename_commit(
    message: Message,
    session: AsyncSession,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    acc_id = data.get("hh_account_id")
    repo = HhLinkedAccountRepository(session)
    acc = await repo.get_by_id(acc_id) if acc_id else None
    if not acc or acc.user_id != user.id:
        await state.clear()
        await message.answer(i18n.get("hh-account-not-found"))
        return
    label = (message.text or "").strip()[:255]
    if not label:
        await message.answer(i18n.get("hh-accounts-rename-empty"))
        return
    await repo.update(acc, label=label)
    await session.commit()
    await state.clear()
    await message.answer(i18n.get("hh-accounts-renamed"))


@router.message(Command("hh_accounts"))
async def cmd_hh_accounts(
    message: Message,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    text, kb = await _hub_message(session, user, i18n)
    await message.answer(text, reply_markup=kb)
