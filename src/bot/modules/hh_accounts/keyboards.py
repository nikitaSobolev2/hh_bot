from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.modules.hh_accounts.callbacks import HhAccountCallback
from src.bot.modules.user_settings.callbacks import SettingsCallback
from src.core.i18n import I18nContext
from src.models.hh_linked_account import HhLinkedAccount


def hh_accounts_hub_keyboard(
    i18n: I18nContext,
    *,
    show_remote_login: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=i18n.get("hh-accounts-add"),
        callback_data=HhAccountCallback(action="add").pack(),
    )
    if show_remote_login:
        builder.button(
            text=i18n.get("hh-accounts-remote-login"),
            callback_data=HhAccountCallback(action="remote_login").pack(),
        )
    builder.button(
        text=i18n.get("btn-back"),
        callback_data=SettingsCallback(action="back").pack(),
    )
    builder.adjust(1)
    return builder.as_markup()


def hh_account_row_keyboard(
    accounts: list[HhLinkedAccount],
    i18n: I18nContext,
    *,
    show_remote_login: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for acc in accounts:
        label = (acc.label or acc.hh_user_id)[:30]
        builder.row(
            InlineKeyboardButton(
                text=f"✏️ {label}",
                callback_data=HhAccountCallback(action="rename", account_id=acc.id).pack(),
            ),
            InlineKeyboardButton(
                text=i18n.get("hh-accounts-remove"),
                callback_data=HhAccountCallback(action="remove", account_id=acc.id).pack(),
            ),
        )
        if acc.browser_storage_enc:
            builder.row(
                InlineKeyboardButton(
                    text=i18n.get("hh-accounts-download-storage"),
                    callback_data=HhAccountCallback(
                        action="download_storage", account_id=acc.id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=i18n.get("hh-accounts-check-session"),
                    callback_data=HhAccountCallback(
                        action="check_session", account_id=acc.id
                    ).pack(),
                ),
            )
    builder.row(
        InlineKeyboardButton(
            text=i18n.get("hh-accounts-add"),
            callback_data=HhAccountCallback(action="add").pack(),
        )
    )
    if show_remote_login:
        builder.row(
            InlineKeyboardButton(
                text=i18n.get("hh-accounts-remote-login"),
                callback_data=HhAccountCallback(action="remote_login").pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=i18n.get("btn-back"),
            callback_data=SettingsCallback(action="back").pack(),
        )
    )
    return builder.as_markup()
