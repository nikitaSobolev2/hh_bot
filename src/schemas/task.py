"""Typed schemas for Celery task notifications sent back to users."""

from __future__ import annotations

from dataclasses import dataclass

from aiogram.types import InlineKeyboardMarkup


@dataclass
class TaskNotification:
    """Structured payload for a task completion notification."""

    chat_id: int
    message_id: int
    text: str
    reply_markup: InlineKeyboardMarkup | None = None
    parse_mode: str = "HTML"
