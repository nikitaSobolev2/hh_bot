"""Keyboard builders for cover letter module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.callbacks.common import MenuCallback
from src.bot.modules.cover_letter.callbacks import CoverLetterCallback

if TYPE_CHECKING:
    from src.core.i18n import I18nContext

_PAGE_SIZE = 10


def cover_letter_hub_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    """Hub: generate new, my letters, back to menu."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("cl-btn-generate-new"),
                    callback_data=CoverLetterCallback(action="generate_new").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("cl-btn-my-letters"),
                    callback_data=CoverLetterCallback(action="list").pack(),
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


def cover_letter_list_keyboard(
    items: list[tuple[int, str, str, int, str]],
    page: int,
    total: int,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    """List of cover letters. items: (task_id, title, date_str, vacancy_id, source)."""
    rows: list[list[InlineKeyboardButton]] = []

    for task_id, title, date_str, vacancy_id, source in items:
        label = f"✉️ {title[:40]}{'…' if len(title) > 40 else ''} — {date_str}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=CoverLetterCallback(
                        action="detail",
                        task_id=task_id,
                        vacancy_id=vacancy_id,
                        source=source,
                    ).pack(),
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
                    callback_data=CoverLetterCallback(action="list", page=page - 1).pack(),
                )
            )
        nav.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{total_pages}",
                callback_data=CoverLetterCallback(action="list", page=page).pack(),
            )
        )
        if page < total_pages - 1:
            nav.append(
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=CoverLetterCallback(action="list", page=page + 1).pack(),
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


def cover_letter_detail_keyboard(
    task_id: int,
    vacancy_id: int,
    source: str,
    vacancy_url: str,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    """Detail view: view vacancy (URL), regenerate, generate one more, back to list."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=i18n.get("cl-btn-view-vacancy"),
                url=vacancy_url,
            )
        ],
        [
            InlineKeyboardButton(
                text=i18n.get("cl-btn-regenerate"),
                callback_data=CoverLetterCallback(
                    action="regenerate",
                    task_id=task_id,
                    vacancy_id=vacancy_id,
                    source=source,
                ).pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text=i18n.get("cl-btn-generate-one-more"),
                callback_data=CoverLetterCallback(action="generate_new").pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=CoverLetterCallback(action="list").pack(),
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def enter_url_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    """Cancel (back to hub) when entering URL."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=CoverLetterCallback(action="cancel_url").pack(),
                )
            ]
        ]
    )
