"""Telegram UI for linking and managing HeadHunter OAuth accounts."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.modules.hh_accounts.callbacks import HhAccountCallback
from src.bot.modules.hh_accounts.keyboards import hh_account_row_keyboard, hh_accounts_hub_keyboard
from src.bot.modules.hh_accounts.states import HhAccountRenameForm
from src.bot.modules.user_settings.callbacks import SettingsCallback
from src.config import settings
from src.core.i18n import I18nContext
from src.models.user import User
from src.repositories.hh_linked_account import HhLinkedAccountRepository
from src.services.hh.oauth_state import generate_state, store_state
from src.services.hh.oauth_tokens import build_authorize_url

router = Router(name="hh_accounts")


def _utc_naive_now():
    return datetime.now(UTC).replace(tzinfo=None)


async def _show_hub(
    callback: CallbackQuery,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    repo = HhLinkedAccountRepository(session)
    accounts = await repo.list_active_for_user(user.id)
    if not accounts:
        text = i18n.get("hh-accounts-empty")
        kb = hh_accounts_hub_keyboard(i18n)
    else:
        lines = [i18n.get("hh-accounts-title"), ""]
        for acc in accounts:
            label = acc.label or acc.hh_user_id
            lines.append(f"• {label}")
        text = "\n".join(lines)
        kb = hh_account_row_keyboard(accounts, i18n)
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
) -> None:
    if not settings.hh_client_id or not settings.hh_oauth_redirect_uri or not settings.hh_token_encryption_key:
        await callback.answer(i18n.get("hh-oauth-not-configured"), show_alert=True)
        return
    state = generate_state()
    await store_state(state, user.telegram_id)
    url = build_authorize_url(state=state)
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
    repo = HhLinkedAccountRepository(session)
    accounts = await repo.list_active_for_user(user.id)
    if not accounts:
        text = i18n.get("hh-accounts-empty")
        kb = hh_accounts_hub_keyboard(i18n)
    else:
        lines = [i18n.get("hh-accounts-title"), ""]
        for acc in accounts:
            label = acc.label or acc.hh_user_id
            lines.append(f"• {label}")
        text = "\n".join(lines)
        kb = hh_account_row_keyboard(accounts, i18n)
    await message.answer(text, reply_markup=kb)
