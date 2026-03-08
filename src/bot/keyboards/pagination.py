from collections.abc import Callable
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.core.i18n import I18nContext


def build_paginated_keyboard(
    items: list[Any],
    item_to_button: Callable[[Any], InlineKeyboardButton],
    page: int,
    has_more: bool,
    page_callback_factory: Callable[[int], str],
    i18n: I18nContext,
    extra_rows: list[list[InlineKeyboardButton]] | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [[item_to_button(item)] for item in items]

    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(
                text=i18n.get("btn-prev"),
                callback_data=page_callback_factory(page - 1),
            )
        )
    if has_more:
        nav_row.append(
            InlineKeyboardButton(
                text=i18n.get("btn-next"),
                callback_data=page_callback_factory(page + 1),
            )
        )
    if nav_row:
        rows.append(nav_row)

    if extra_rows:
        rows.extend(extra_rows)

    return InlineKeyboardMarkup(inline_keyboard=rows)
