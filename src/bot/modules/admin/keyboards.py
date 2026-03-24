from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.callbacks.common import MenuCallback
from src.bot.keyboards.pagination import build_paginated_keyboard
from src.bot.modules.admin.callbacks import AdminCallback, AdminSettingCallback, AdminUserCallback
from src.core.i18n import I18nContext
from src.models.user import User

MANAGED_SETTINGS = [
    ("openai_base_url", "OpenAI Base URL", "text"),
    ("openai_api_key", "OpenAI API Key", "text"),
    ("openai_model", "OpenAI Model", "text"),
    ("payment_enabled", "Payment Enabled", "toggle"),
    ("log_telegram_chat_id", "Logging Chat ID", "text"),
    ("support_chat_id", "Support Chat ID", "text"),
    ("blacklist_days", "Blacklist Duration (days)", "text"),
    ("task_parsing_enabled", "Parsing Task Enabled", "toggle"),
    # ("task_parsing_timeout_seconds", "Parsing Task Timeout (s)", "text"),
    ("task_keyphrase_enabled", "Key Phrases Task Enabled", "toggle"),
    # ("task_keyphrase_timeout_seconds", "Key Phrases Task Timeout (s)", "text"),
    ("parsing_staleness_window_seconds", "Parsing Staleness Window (s)", "text"),
    ("cb_parsing_failure_threshold", "CB Parsing Failure Threshold", "text"),
    ("cb_parsing_recovery_timeout", "CB Parsing Recovery Timeout (s)", "text"),
    ("cb_keyphrase_failure_threshold", "CB Key Phrases Failure Threshold", "text"),
    ("cb_keyphrase_recovery_timeout", "CB Key Phrases Recovery Timeout (s)", "text"),
    ("task_autoparse_enabled", "Autoparse Task Enabled", "toggle"),
    ("task_autorespond_enabled", "Autorespond Task Enabled", "toggle"),
    ("autoparse_interval_hours", "Autoparse Interval (hours)", "text"),
    (
        "autoparse_target_count",
        "Autoparse Target Count per Run",
        "select",
        [(10, "10"), (30, "30"), (50, "50"), (5000, "admin-autoparse-target-all")],
    ),
]

AUTOPARSE_TARGET_VALID = {10, 30, 50, 5000}


def admin_menu_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-users"),
                    callback_data=AdminCallback(action="users").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-app-settings"),
                    callback_data=AdminCallback(action="settings").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-support"),
                    callback_data=AdminCallback(action="support").pack(),
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


def user_list_keyboard(
    users: list[User], page: int, has_more: bool, i18n: I18nContext
) -> InlineKeyboardMarkup:
    def _user_button(u: User) -> InlineKeyboardButton:
        status = "🚫" if u.is_banned else "✅"
        return InlineKeyboardButton(
            text=f"{status} {u.first_name} (@{u.username or '—'})",
            callback_data=AdminUserCallback(action="detail", user_id=u.id).pack(),
        )

    return build_paginated_keyboard(
        items=users,
        item_to_button=_user_button,
        page=page,
        has_more=has_more,
        page_callback_factory=lambda p: AdminUserCallback(action="list", page=p).pack(),
        i18n=i18n,
        extra_rows=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-search"),
                    callback_data=AdminUserCallback(action="search").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=AdminCallback(action="back").pack(),
                )
            ],
        ],
    )


def user_detail_keyboard(target_user: User, i18n: I18nContext) -> InlineKeyboardMarkup:
    ban_text = i18n.get("btn-unban") if target_user.is_banned else i18n.get("btn-ban")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=ban_text,
                    callback_data=AdminUserCallback(
                        action="toggle_ban", user_id=target_user.id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-adjust-balance"),
                    callback_data=AdminUserCallback(
                        action="balance", user_id=target_user.id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-send-message"),
                    callback_data=AdminUserCallback(
                        action="message", user_id=target_user.id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back-users"),
                    callback_data=AdminUserCallback(action="list", page=0).pack(),
                )
            ],
        ],
    )


def settings_list_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in MANAGED_SETTINGS:
        key, label, _stype = item[0], item[1], item[2]
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=AdminSettingCallback(action="view", key=key).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=AdminCallback(action="back").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_settings_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back-settings"),
                    callback_data=AdminSettingCallback(action="list").pack(),
                )
            ]
        ]
    )


def setting_detail_keyboard(
    key: str, stype: str, i18n: I18nContext, choices: list[tuple[int, str]] | None = None
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if stype == "toggle":
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-toggle"),
                    callback_data=AdminSettingCallback(action="toggle", key=key).pack(),
                )
            ]
        )
    elif stype == "select" and choices:
        for val, label in choices:
            btn_text = i18n.get(label) if label.startswith("admin-") else label
            rows.append(
                [
                    InlineKeyboardButton(
                        text=btn_text,
                        callback_data=AdminSettingCallback(
                            action="select_value", key=key, value=str(val)
                        ).pack(),
                    )
                ]
            )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-edit"),
                    callback_data=AdminSettingCallback(action="edit", key=key).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back-settings"),
                callback_data=AdminSettingCallback(action="list").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
