"""Keyboard builders for the shared Work Experience module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.modules.work_experience.callbacks import WorkExpCallback

if TYPE_CHECKING:
    from src.core.i18n import I18nContext
    from src.models.work_experience import UserWorkExperience

MAX_WORK_EXPERIENCES = 6


def work_experience_keyboard(
    experiences: list[UserWorkExperience],
    return_to: str,
    i18n: I18nContext,
    *,
    show_continue: bool = False,
    show_skip: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for exp in experiences:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"\u274c {i18n.get('btn-remove')} {exp.company_name}",
                    callback_data=WorkExpCallback(
                        action="remove",
                        work_exp_id=exp.id,
                        return_to=return_to,
                    ).pack(),
                )
            ]
        )

    if len(experiences) < MAX_WORK_EXPERIENCES:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-add-company"),
                    callback_data=WorkExpCallback(
                        action="add",
                        return_to=return_to,
                    ).pack(),
                )
            ]
        )

    if show_skip:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-skip"),
                    callback_data=WorkExpCallback(
                        action="skip",
                        return_to=return_to,
                    ).pack(),
                )
            ]
        )

    if show_continue and experiences:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-continue"),
                    callback_data=WorkExpCallback(
                        action="continue",
                        return_to=return_to,
                    ).pack(),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=WorkExpCallback(
                    action="back",
                    return_to=return_to,
                ).pack(),
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_add_keyboard(return_to: str, i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=WorkExpCallback(
                        action="cancel_add",
                        return_to=return_to,
                    ).pack(),
                )
            ]
        ]
    )
