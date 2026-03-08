from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.callbacks.common import MenuCallback
from src.bot.modules.user_settings.callbacks import BlacklistCallback, SettingsCallback
from src.core.i18n import I18nContext


def settings_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-language"),
                    callback_data=SettingsCallback(action="language").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-clear-blacklist"),
                    callback_data=SettingsCallback(action="clear_blacklist").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-notifications"),
                    callback_data=SettingsCallback(action="notifications").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-topup"),
                    callback_data=SettingsCallback(action="topup").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-delete-data"),
                    callback_data=SettingsCallback(action="delete_data").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=MenuCallback(action="main").pack(),
                )
            ],
        ]
    )


def language_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🇷🇺 Русский",
                    callback_data=SettingsCallback(action="set_lang", value="ru").pack(),
                ),
                InlineKeyboardButton(
                    text="🇬🇧 English",
                    callback_data=SettingsCallback(action="set_lang", value="en").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=MenuCallback(action="settings").pack(),
                )
            ],
        ]
    )


def blacklist_management_keyboard(
    contexts: list[tuple[str, int]],
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for ctx_name, _count in contexts:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-clear-context", context=ctx_name[:30]),
                    callback_data=BlacklistCallback(
                        action="clear_ctx", context=ctx_name[:50]
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-clear-all"),
                callback_data=BlacklistCallback(action="clear_all").pack(),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=SettingsCallback(action="back").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
