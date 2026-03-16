"""Keyboard builders for the Achievement Generator module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.callbacks.common import MenuCallback
from src.bot.modules.achievements.callbacks import AchievementCallback

if TYPE_CHECKING:
    from src.core.i18n import I18nContext
    from src.models.achievement import AchievementGeneration

_PAGE_SIZE = 5


def achievement_list_keyboard(
    generations: list[AchievementGeneration],
    page: int,
    total: int,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=i18n.get("ach-btn-generate-new"),
                callback_data=AchievementCallback(action="generate_new").pack(),
            )
        ]
    ]

    for gen in generations:
        date_str = gen.created_at.strftime("%m/%d %H:%M")
        item_count = len(gen.items)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🏆 {date_str} ({item_count} {i18n.get('ach-companies-count')})",
                    callback_data=AchievementCallback(action="detail", generation_id=gen.id).pack(),
                )
            ]
        )

    total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=AchievementCallback(action="list", page=page - 1).pack(),
                )
            )
        nav.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{total_pages}",
                callback_data=AchievementCallback(action="list", page=page).pack(),
            )
        )
        if page < total_pages - 1:
            nav.append(
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=AchievementCallback(action="list", page=page + 1).pack(),
                )
            )
        rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back-menu"),
                callback_data=MenuCallback(action="main").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def achievement_detail_keyboard(
    generation_id: int,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("ach-btn-delete"),
                    callback_data=AchievementCallback(
                        action="delete", generation_id=generation_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=AchievementCallback(action="list").pack(),
                )
            ],
        ]
    )


def achievement_input_keyboard(
    company_name: str,
    exp_index: int,
    total: int,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-skip"),
                    callback_data=AchievementCallback(
                        action="skip_input",
                        item_id=exp_index,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=AchievementCallback(action="list").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=AchievementCallback(action="cancel").pack(),
                )
            ],
        ]
    )


def achievement_proceed_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("ach-btn-proceed"),
                    callback_data=AchievementCallback(action="proceed").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=AchievementCallback(action="list").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=AchievementCallback(action="cancel").pack(),
                )
            ],
        ]
    )
