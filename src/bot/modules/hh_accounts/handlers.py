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
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.modules.autoparse.keyboards import parse_login_required_keyboard
from src.bot.modules.autoparse.states import AutoparseEditForm, AutoparseForm
from src.bot.modules.hh_accounts.callbacks import HhAccountCallback
from src.bot.modules.hh_accounts.keyboards import hh_account_row_keyboard, hh_accounts_hub_keyboard
from src.bot.modules.hh_accounts.states import HhAccountRenameForm, HhBrowserImportForm
from src.bot.modules.user_settings.callbacks import SettingsCallback
from src.config import settings
from src.core.celery_async import normalize_celery_task_id, run_celery_task, run_sync_in_thread
from src.core.i18n import I18nContext
from src.models.user import User
from src.repositories.hh_linked_account import HhLinkedAccountRepository
from src.services.hh.crypto import HhTokenCipher
from src.services.hh.linked_account_browser_storage import persist_browser_storage_state_for_user
from src.services.hh.oauth_state import generate_state, store_state
from src.services.hh.oauth_tokens import build_authorize_url
from src.services.hh_ui.applicant_negotiations_http import check_negotiations_browser_session_available
from src.services.hh_ui.browser_link import validate_logged_in_playwright_storage_state
from src.services.hh_ui.config import HhUiApplyConfig
from src.services.hh_ui.storage import decrypt_browser_storage
from src.worker.tasks.hh_login_assist import hh_login_assist_task

router = Router(name="hh_accounts")

_VALIDATION_ERROR_I18N = {
    "not-a-json-object": "hh-accounts-browser-err-not-object",
    "missing-cookies-array": "hh-accounts-browser-err-no-cookies",
    "no-hh-cookies": "hh-accounts-browser-err-no-hh",
    "not-logged-in": "hh-accounts-browser-err-not-logged-in",
}


def _utc_naive_now():
    return datetime.now(UTC).replace(tzinfo=None)


def _safe_storage_export_filename(hh_user_id: str) -> str:
    part = "".join(c if c.isalnum() or c in "-_" else "_" for c in (hh_user_id or "")[:48])
    return f"hh_storage_{part or 'account'}.json"


def _oauth_configured() -> bool:
    return bool(
        settings.hh_client_id
        and settings.hh_oauth_redirect_uri
        and settings.hh_token_encryption_key
    )


def _browser_import_configured() -> bool:
    return bool(settings.hh_ui_apply_enabled and settings.hh_token_encryption_key)


def _login_assist_available() -> bool:
    return bool(
        settings.hh_login_assist_enabled
        and settings.hh_ui_apply_enabled
        and settings.hh_token_encryption_key
    )


async def _hub_message(
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> tuple[str, InlineKeyboardMarkup]:
    repo = HhLinkedAccountRepository(session)
    accounts = await repo.list_active_for_user(user.id)
    show_remote = _login_assist_available()
    if not accounts:
        return i18n.get("hh-accounts-empty"), hh_accounts_hub_keyboard(
            i18n, show_remote_login=show_remote
        )
    lines = [i18n.get("hh-accounts-title"), ""]
    for acc in accounts:
        label = acc.label or acc.hh_user_id
        lines.append(f"• {label}")
    text = "\n".join(lines)
    kb = hh_account_row_keyboard(accounts, i18n, show_remote_login=show_remote)
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


@router.callback_query(HhAccountCallback.filter(F.action == "check_session"))
async def hh_check_session(
    callback: CallbackQuery,
    callback_data: HhAccountCallback,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    if not _browser_import_configured():
        await callback.answer(i18n.get("hh-link-not-available"), show_alert=True)
        return
    repo = HhLinkedAccountRepository(session)
    acc = await repo.get_by_id(callback_data.account_id)
    if not acc or acc.user_id != user.id:
        await callback.answer(i18n.get("hh-account-not-found"), show_alert=True)
        return
    if not acc.browser_storage_enc:
        await callback.answer(i18n.get("hh-accounts-download-storage-none"), show_alert=True)
        return
    cipher = HhTokenCipher(settings.hh_token_encryption_key)
    try:
        storage = decrypt_browser_storage(acc.browser_storage_enc, cipher)
    except ValueError:
        await callback.answer(i18n.get("hh-accounts-download-storage-failed"), show_alert=True)
        return
    if not storage:
        await callback.answer(i18n.get("hh-accounts-download-storage-none"), show_alert=True)
        return
    cfg = HhUiApplyConfig.from_settings()
    status, detail = await run_sync_in_thread(
        check_negotiations_browser_session_available, storage, cfg
    )
    label = (acc.label or acc.hh_user_id)[:200]
    if status == "ok":
        await callback.answer(i18n.get("hh-accounts-session-check-ok"), show_alert=True)
        return
    if status == "login":
        body = i18n.get("hh-accounts-session-check-fail-login", label=label)
    elif status == "unexpected_url":
        body = i18n.get("hh-accounts-session-check-fail-unexpected", label=label)
    else:
        d = (detail or "error")[:200]
        body = i18n.get("hh-accounts-session-check-fail-error", label=label, detail=d)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("hh-accounts-remove"),
                    callback_data=HhAccountCallback(action="remove", account_id=acc.id).pack(),
                ),
                InlineKeyboardButton(
                    text=i18n.get("hh-accounts-replace-session"),
                    callback_data=HhAccountCallback(action="replace_session", account_id=acc.id).pack(),
                ),
            ],
        ]
    )
    await callback.message.answer(body, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(HhAccountCallback.filter(F.action == "replace_session"))
async def hh_replace_session(
    callback: CallbackQuery,
    callback_data: HhAccountCallback,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    if not _login_assist_available():
        await callback.answer(i18n.get("hh-login-assist-disabled"), show_alert=True)
        return
    repo = HhLinkedAccountRepository(session)
    acc = await repo.get_by_id(callback_data.account_id)
    if not acc or acc.user_id != user.id:
        await callback.answer(i18n.get("hh-account-not-found"), show_alert=True)
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=HhAccountCallback(action="cancel_login_assist").pack(),
                )
            ],
        ]
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("hh-login-assist-starting"),
            reply_markup=kb,
        )
    await callback.answer()
    await run_celery_task(
        hh_login_assist_task,
        user.id,
        callback.message.chat.id,
        callback.message.message_id,
        i18n.locale,
        hh_linked_account_id=acc.id,
    )


@router.callback_query(HhAccountCallback.filter(F.action == "remote_login"))
async def hh_remote_login(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    if not _login_assist_available():
        await callback.answer(i18n.get("hh-login-assist-disabled"), show_alert=True)
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=HhAccountCallback(action="cancel_login_assist").pack(),
                )
            ],
        ]
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("hh-login-assist-starting"),
            reply_markup=kb,
        )
    await callback.answer()
    await run_celery_task(
        hh_login_assist_task,
        user.id,
        callback.message.chat.id,
        callback.message.message_id,
        i18n.locale,
    )


@router.callback_query(HhAccountCallback.filter(F.action == "cancel_login_assist"))
async def hh_cancel_login_assist(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    from src.core.celery_async import run_sync_in_thread
    from src.core.redis import create_async_redis
    from src.worker.app import celery_app
    from src.worker.tasks.hh_login_assist import clear_active_job_for_user, get_active_job_id

    tid = await run_sync_in_thread(get_active_job_id, user.id)
    if tid:
        revoke_id = normalize_celery_task_id(tid)
        if revoke_id:
            await run_sync_in_thread(
                lambda rid=revoke_id: celery_app.control.revoke(rid, terminate=True)
            )
    await run_sync_in_thread(clear_active_job_for_user, user.id)
    r = create_async_redis()
    try:
        await r.delete(f"lock:user_task:hh_login_assist:{user.id}")
    finally:
        await r.aclose()
    await _show_hub(callback, session, user, i18n)
    await callback.answer(i18n.get("hh-login-assist-cancelled"))


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
        state_dict = validate_logged_in_playwright_storage_state(parsed)
    except ValueError as exc:
        code = str(exc.args[0]) if exc.args else "unknown"
        msg_key = _VALIDATION_ERROR_I18N.get(code, "hh-accounts-browser-err-unknown")
        await message.answer(i18n.get(msg_key))
        return

    cipher = HhTokenCipher(settings.hh_token_encryption_key)
    await persist_browser_storage_state_for_user(session, user.id, state_dict, cipher=cipher)
    await session.commit()
    state_data = await state.get_data()
    pending_flow = state_data.get("parse_pending_flow")
    pending_company_id = int(state_data.get("parse_pending_company_id") or 0)
    if pending_flow == "create":
        await state.set_state(AutoparseForm.parse_hh_account)
    elif pending_flow:
        await state.set_state(AutoparseEditForm.edit_parse_mode)
    else:
        await state.clear()

    text, kb = await _hub_message(session, user, i18n)
    await message.answer(i18n.get("hh-accounts-browser-import-success"))
    await message.answer(text, reply_markup=kb)
    if pending_flow:
        await message.answer(
            i18n.get("autoparse-parse-login-followup"),
            reply_markup=parse_login_required_keyboard(
                i18n,
                company_id=pending_company_id,
                back_action="hub" if pending_flow == "create" else "detail",
            ),
        )


@router.message(HhBrowserImportForm.waiting_json)
async def hh_browser_import_reminder(message: Message, i18n: I18nContext) -> None:
    await message.answer(i18n.get("hh-accounts-browser-import-send-file"))


@router.callback_query(HhAccountCallback.filter(F.action == "download_storage"))
async def hh_download_browser_storage(
    callback: CallbackQuery,
    callback_data: HhAccountCallback,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    if not settings.hh_token_encryption_key:
        await callback.answer(i18n.get("hh-link-not-available"), show_alert=True)
        return
    repo = HhLinkedAccountRepository(session)
    acc = await repo.get_by_id(callback_data.account_id)
    if not acc or acc.user_id != user.id:
        await callback.answer(i18n.get("hh-account-not-found"), show_alert=True)
        return
    if not acc.browser_storage_enc:
        await callback.answer(i18n.get("hh-accounts-download-storage-none"), show_alert=True)
        return
    cipher = HhTokenCipher(settings.hh_token_encryption_key)
    try:
        state = decrypt_browser_storage(acc.browser_storage_enc, cipher)
    except ValueError:
        await callback.answer(i18n.get("hh-accounts-download-storage-failed"), show_alert=True)
        return
    if not state:
        await callback.answer(i18n.get("hh-accounts-download-storage-none"), show_alert=True)
        return
    payload = json.dumps(state, ensure_ascii=False, indent=2)
    doc = BufferedInputFile(
        payload.encode("utf-8"),
        filename=_safe_storage_export_filename(acc.hh_user_id),
    )
    await callback.message.answer_document(
        doc,
        caption=i18n.get("hh-accounts-download-storage-caption"),
    )
    await callback.answer()


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
