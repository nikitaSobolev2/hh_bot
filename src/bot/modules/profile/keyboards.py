from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.callbacks.common import MenuCallback
from src.bot.modules.profile.callbacks import ProfileCallback


def profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Stats",
                    callback_data=ProfileCallback(action="stats").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔗 Referral Link",
                    callback_data=ProfileCallback(action="referral").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Back",
                    callback_data=MenuCallback(action="main").pack(),
                )
            ],
        ]
    )
