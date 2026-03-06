from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.callbacks.common import MenuCallback


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔍 New Parsing",
                    callback_data=MenuCallback(action="new_parsing").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📋 My Parsings",
                    callback_data=MenuCallback(action="my_parsings").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="👤 Profile",
                    callback_data=MenuCallback(action="profile").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚙️ Settings",
                    callback_data=MenuCallback(action="settings").pack(),
                )
            ],
        ]
    )


def main_menu_admin_keyboard() -> InlineKeyboardMarkup:
    kb = main_menu_keyboard()
    kb.inline_keyboard.append(
        [
            InlineKeyboardButton(
                text="🛠 Admin Panel",
                callback_data=MenuCallback(action="admin").pack(),
            )
        ]
    )
    return kb


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="◀️ Back to Menu",
                    callback_data=MenuCallback(action="main").pack(),
                )
            ],
        ]
    )
