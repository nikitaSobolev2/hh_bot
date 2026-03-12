"""Keyboard builders for the Resume Generator module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.callbacks.common import MenuCallback
from src.bot.modules.resume.callbacks import ResumeCallback

if TYPE_CHECKING:
    from src.core.i18n import I18nContext


def resume_start_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("res-btn-start"),
                    callback_data=ResumeCallback(action="start").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back-menu"),
                    callback_data=MenuCallback(action="main").pack(),
                )
            ],
        ]
    )


def resume_result_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("res-btn-create-autoparser"),
                    callback_data=ResumeCallback(action="create_autoparser").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back-menu"),
                    callback_data=MenuCallback(action="main").pack(),
                )
            ],
        ]
    )


def resume_cancel_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=ResumeCallback(action="cancel").pack(),
                )
            ]
        ]
    )
