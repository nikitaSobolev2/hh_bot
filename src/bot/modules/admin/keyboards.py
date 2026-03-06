from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.callbacks.common import MenuCallback
from src.bot.keyboards.pagination import build_paginated_keyboard
from src.bot.modules.admin.callbacks import AdminCallback, AdminSettingCallback, AdminUserCallback
from src.models.user import User

_BACK = "◀️ Back"

MANAGED_SETTINGS = [
    ("openai_base_url", "OpenAI Base URL", "text"),
    ("openai_api_key", "OpenAI API Key", "text"),
    ("openai_model", "OpenAI Model", "text"),
    ("payment_enabled", "Payment Enabled", "toggle"),
    ("logging_chat_id", "Logging Chat ID", "text"),
    ("support_chat_id", "Support Chat ID", "text"),
    ("blacklist_days", "Blacklist Duration (days)", "text"),
    ("task_parsing_enabled", "Parsing Task Enabled", "toggle"),
    ("task_parsing_timeout_seconds", "Parsing Task Timeout (s)", "text"),
    ("task_keyphrase_enabled", "Key Phrases Task Enabled", "toggle"),
    ("task_keyphrase_timeout_seconds", "Key Phrases Task Timeout (s)", "text"),
    ("cb_parsing_failure_threshold", "CB Parsing Failure Threshold", "text"),
    ("cb_parsing_recovery_timeout", "CB Parsing Recovery Timeout (s)", "text"),
    ("cb_keyphrase_failure_threshold", "CB Key Phrases Failure Threshold", "text"),
    ("cb_keyphrase_recovery_timeout", "CB Key Phrases Recovery Timeout (s)", "text"),
]


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👥 Users",
                    callback_data=AdminCallback(action="users").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚙️ App Settings",
                    callback_data=AdminCallback(action="settings").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📬 Support Inbox",
                    callback_data=AdminCallback(action="support").pack(),
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


def user_list_keyboard(users: list[User], page: int, has_more: bool) -> InlineKeyboardMarkup:
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
        extra_rows=[
            [
                InlineKeyboardButton(
                    text="🔍 Search",
                    callback_data=AdminUserCallback(action="search").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_BACK,
                    callback_data=AdminCallback(action="back").pack(),
                )
            ],
        ],
    )


def user_detail_keyboard(target_user: User) -> InlineKeyboardMarkup:
    ban_text = "✅ Unban" if target_user.is_banned else "🚫 Ban"
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
                    text="💰 Adjust Balance",
                    callback_data=AdminUserCallback(
                        action="balance", user_id=target_user.id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="✉️ Send Message",
                    callback_data=AdminUserCallback(
                        action="message", user_id=target_user.id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Back to Users",
                    callback_data=AdminUserCallback(action="list", page=0).pack(),
                )
            ],
        ],
    )


def settings_list_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for key, label, _stype in MANAGED_SETTINGS:
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
                text=_BACK,
                callback_data=AdminCallback(action="back").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="◀️ Back to Settings",
                    callback_data=AdminSettingCallback(action="list").pack(),
                )
            ]
        ]
    )


def setting_detail_keyboard(key: str, stype: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if stype == "toggle":
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔄 Toggle",
                    callback_data=AdminSettingCallback(action="toggle", key=key).pack(),
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✏️ Edit",
                    callback_data=AdminSettingCallback(action="edit", key=key).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="◀️ Back to Settings",
                callback_data=AdminSettingCallback(action="list").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
