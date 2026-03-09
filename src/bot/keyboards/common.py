from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.callbacks.common import MenuCallback
from src.core.i18n import I18nContext


def main_menu_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-new-parsing"),
                    callback_data=MenuCallback(action="new_parsing").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-my-parsings"),
                    callback_data=MenuCallback(action="my_parsings").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-autoparse"),
                    callback_data=MenuCallback(action="autoparse").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-profile"),
                    callback_data=MenuCallback(action="profile").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-settings"),
                    callback_data=MenuCallback(action="settings").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-support-user"),
                    callback_data=MenuCallback(action="support").pack(),
                )
            ],
        ]
    )


def main_menu_admin_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    kb = main_menu_keyboard(i18n)
    kb.inline_keyboard.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-admin"),
                callback_data=MenuCallback(action="admin").pack(),
            )
        ]
    )
    return kb


def back_to_menu_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back-menu"),
                    callback_data=MenuCallback(action="main").pack(),
                )
            ],
        ]
    )
