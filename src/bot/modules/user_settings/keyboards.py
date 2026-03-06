from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.callbacks.common import MenuCallback
from src.bot.modules.user_settings.callbacks import BlacklistCallback, SettingsCallback

_BACK = "◀️ Back"


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🌐 Language",
                    callback_data=SettingsCallback(action="language").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Clear Blacklist",
                    callback_data=SettingsCallback(action="clear_blacklist").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔔 Notifications",
                    callback_data=SettingsCallback(action="notifications").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="💰 Top Up Balance",
                    callback_data=SettingsCallback(action="topup").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚠️ Delete My Data",
                    callback_data=SettingsCallback(action="delete_data").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_BACK,
                    callback_data=MenuCallback(action="main").pack(),
                )
            ],
        ]
    )


def language_keyboard() -> InlineKeyboardMarkup:
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
                    text=_BACK,
                    callback_data=MenuCallback(action="settings").pack(),
                )
            ],
        ]
    )


def blacklist_management_keyboard(
    contexts: list[tuple[str, int]],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for ctx_name, _count in contexts:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🗑 Clear: {ctx_name[:30]}",
                    callback_data=BlacklistCallback(
                        action="clear_ctx", context=ctx_name[:50]
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🗑 Clear All",
                callback_data=BlacklistCallback(action="clear_all").pack(),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=_BACK,
                callback_data=SettingsCallback(action="back").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
