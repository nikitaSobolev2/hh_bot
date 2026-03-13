"""Shared keyboard factory functions for common patterns.

Rules applied by all builders here:
- Primary action: top-left
- Max 2 buttons per action row
- Pagination row: second-to-last
- Back/Cancel: last row, full width
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.callbacks.common import MenuCallback
from src.core.i18n import I18nContext


def cancel_keyboard(
    cancel_callback: str,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    """Single-button keyboard with a localised Cancel button."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=i18n.get("btn-cancel"),
        callback_data=cancel_callback,
    )
    return builder.as_markup()


def back_to_section_keyboard(
    back_callback: str,
    i18n: I18nContext,
    *,
    back_key: str = "btn-back",
) -> InlineKeyboardMarkup:
    """Single-button keyboard with a Back button."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=i18n.get(back_key),
        callback_data=back_callback,
    )
    return builder.as_markup()


def confirm_keyboard(
    confirm_callback: str,
    cancel_callback: str,
    i18n: I18nContext,
    *,
    confirm_key: str = "btn-confirm",
    cancel_key: str = "btn-cancel",
) -> InlineKeyboardMarkup:
    """Two-button confirmation keyboard (confirm | cancel)."""
    builder = InlineKeyboardBuilder()
    builder.button(text=i18n.get(confirm_key), callback_data=confirm_callback)
    builder.button(text=i18n.get(cancel_key), callback_data=cancel_callback)
    builder.adjust(2)
    return builder.as_markup()


def pagination_keyboard(
    items: list[tuple[str, str]],
    page: int,
    total: int,
    page_size: int,
    prev_callback: str,
    next_callback: str,
    back_callback: str,
    i18n: I18nContext,
    *,
    columns: int = 1,
) -> InlineKeyboardMarkup:
    """Generic paginated list keyboard.

    Args:
        items: List of (label, callback_data) tuples for the current page.
        page: Current page (0-indexed).
        total: Total number of items.
        page_size: Items per page.
        prev_callback: Callback data for the « prev button.
        next_callback: Callback data for the » next button.
        back_callback: Callback data for the ← back button.
        i18n: Translation context.
        columns: Buttons per row for item buttons.
    """
    builder = InlineKeyboardBuilder()

    for label, callback_data in items:
        builder.button(text=label, callback_data=callback_data)

    if columns > 1:
        builder.adjust(*([columns] * (len(items) // columns + 1)))
    else:
        builder.adjust(1)

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="«", callback_data=prev_callback))
    if (page + 1) * page_size < total:
        nav_buttons.append(InlineKeyboardButton(text="»", callback_data=next_callback))
    if nav_buttons:
        builder.row(*nav_buttons)

    builder.row(InlineKeyboardButton(text=i18n.get("btn-back"), callback_data=back_callback))
    return builder.as_markup()


def back_to_main_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    """Simple back-to-main-menu button."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=i18n.get("btn-back-menu"),
        callback_data=MenuCallback(action="main").pack(),
    )
    return builder.as_markup()
