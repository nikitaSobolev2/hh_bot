from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.callbacks.common import MenuCallback
from src.bot.modules.user_settings.callbacks import (
    BlacklistCallback,
    SettingsCallback,
    TimezoneCallback,
)
from src.core.i18n import I18nContext

_UTC_PLUS_1 = "UTC+1"
_UTC_PLUS_2 = "UTC+2"
_UTC_PLUS_3 = "UTC+3"
_UTC_PLUS_4 = "UTC+4"
_UTC_PLUS_7 = "UTC+7"
_UTC_PLUS_8 = "UTC+8"
_UTC_PLUS_9 = "UTC+9"

POPULAR_TIMEZONES: list[tuple[str, str]] = [
    ("Pacific/Midway", "UTC-11"),
    ("Pacific/Honolulu", "UTC-10"),
    ("America/Anchorage", "UTC-9"),
    ("America/Los_Angeles", "UTC-8"),
    ("America/Denver", "UTC-7"),
    ("America/Chicago", "UTC-6"),
    ("America/New_York", "UTC-5"),
    ("America/Caracas", "UTC-4"),
    ("America/Argentina/Buenos_Aires", "UTC-3"),
    ("America/Sao_Paulo", "UTC-3"),
    ("Atlantic/South_Georgia", "UTC-2"),
    ("Atlantic/Azores", "UTC-1"),
    ("UTC", "UTC+0"),
    ("Europe/London", "UTC+0"),
    ("Europe/Berlin", _UTC_PLUS_1),
    ("Europe/Paris", _UTC_PLUS_1),
    ("Europe/Warsaw", _UTC_PLUS_1),
    ("Europe/Istanbul", _UTC_PLUS_3),
    ("Europe/Helsinki", _UTC_PLUS_2),
    ("Europe/Bucharest", _UTC_PLUS_2),
    ("Europe/Kiev", _UTC_PLUS_2),
    ("Europe/Athens", _UTC_PLUS_2),
    ("Africa/Cairo", _UTC_PLUS_2),
    ("Europe/Moscow", _UTC_PLUS_3),
    ("Europe/Minsk", _UTC_PLUS_3),
    ("Asia/Riyadh", _UTC_PLUS_3),
    ("Asia/Tehran", "UTC+3:30"),
    ("Asia/Dubai", _UTC_PLUS_4),
    ("Europe/Samara", _UTC_PLUS_4),
    ("Asia/Tbilisi", _UTC_PLUS_4),
    ("Asia/Yerevan", _UTC_PLUS_4),
    ("Asia/Baku", _UTC_PLUS_4),
    ("Asia/Tashkent", "UTC+5"),
    ("Asia/Yekaterinburg", "UTC+5"),
    ("Asia/Kolkata", "UTC+5:30"),
    ("Asia/Almaty", "UTC+6"),
    ("Asia/Omsk", "UTC+6"),
    ("Asia/Bangkok", _UTC_PLUS_7),
    ("Asia/Krasnoyarsk", _UTC_PLUS_7),
    ("Asia/Jakarta", _UTC_PLUS_7),
    ("Asia/Shanghai", _UTC_PLUS_8),
    ("Asia/Singapore", _UTC_PLUS_8),
    ("Asia/Irkutsk", _UTC_PLUS_8),
    ("Asia/Hong_Kong", _UTC_PLUS_8),
    ("Asia/Tokyo", _UTC_PLUS_9),
    ("Asia/Yakutsk", _UTC_PLUS_9),
    ("Asia/Seoul", _UTC_PLUS_9),
    ("Australia/Sydney", "UTC+10"),
    ("Asia/Vladivostok", "UTC+10"),
    ("Pacific/Auckland", "UTC+12"),
    ("Asia/Kamchatka", "UTC+12"),
]

_TZ_PER_PAGE = 8


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
                    text=i18n.get("btn-timezone"),
                    callback_data=SettingsCallback(action="timezone").pack(),
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


def timezone_keyboard(
    page: int,
    i18n: I18nContext,
    search_query: str | None = None,
) -> InlineKeyboardMarkup:
    zones = POPULAR_TIMEZONES
    if search_query:
        q = search_query.lower()
        zones = [(tz, off) for tz, off in zones if q in tz.lower() or q in off.lower()]

    total = len(zones)
    start = page * _TZ_PER_PAGE
    page_items = zones[start : start + _TZ_PER_PAGE]

    rows: list[list[InlineKeyboardButton]] = []
    for tz_name, offset in page_items:
        label = tz_name.replace("_", " ")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{label} ({offset})",
                    callback_data=TimezoneCallback(action="select", value=tz_name).pack(),
                )
            ]
        )

    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(
                text="<",
                callback_data=TimezoneCallback(action="page", page=page - 1).pack(),
            )
        )
    if start + _TZ_PER_PAGE < total:
        nav_row.append(
            InlineKeyboardButton(
                text=">",
                callback_data=TimezoneCallback(action="page", page=page + 1).pack(),
            )
        )
    if nav_row:
        rows.append(nav_row)

    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-tz-search"),
                callback_data=TimezoneCallback(action="search").pack(),
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
