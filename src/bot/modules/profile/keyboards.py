from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from src.core.i18n import I18nContext

from src.bot.callbacks.common import MenuCallback
from src.bot.modules.profile.callbacks import ProfileCallback


def profile_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-stats"),
                    callback_data=ProfileCallback(action="stats").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-referral"),
                    callback_data=ProfileCallback(action="referral").pack(),
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
