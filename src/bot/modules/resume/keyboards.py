"""Keyboard builders for the Resume Generator module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.callbacks.common import MenuCallback
from src.bot.modules.resume.callbacks import ResumeCallback

if TYPE_CHECKING:
    from src.core.i18n import I18nContext
    from src.models.parsing import ParsingCompany


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


def resume_keywords_source_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    """Ask the user where their extra keywords should come from."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("res-btn-keywords-manual"),
                    callback_data=ResumeCallback(action="keywords_manual").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("res-btn-keywords-from-parsing"),
                    callback_data=ResumeCallback(action="keywords_from_parsing").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-skip"),
                    callback_data=ResumeCallback(action="keywords_skip").pack(),
                )
            ],
        ]
    )


def resume_parsing_companies_keyboard(
    companies: list[ParsingCompany],
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    """One button per parsing company that has aggregated keywords, plus a Skip."""
    rows = [
        [
            InlineKeyboardButton(
                text=company.vacancy_title,
                callback_data=ResumeCallback(
                    action="keywords_use_company",
                    company_id=company.id,
                ).pack(),
            )
        ]
        for company in companies
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-skip"),
                callback_data=ResumeCallback(action="keywords_skip").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
