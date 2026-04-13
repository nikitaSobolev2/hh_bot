"""TelegramMessenger — shared Telegram notification helper for Celery tasks.

Provides a unified ``edit_or_send`` pattern used by all task completion
notifications:

1. Try ``edit_message_text`` on the original processing message.
2. If it fails (message deleted, too old, etc.), fall back to ``send_message``.

Also exposes ``send_message_with_retry`` (previously private ``_send_with_retry``
in streaming.py) as a public API so tasks can send messages reliably.
"""

from __future__ import annotations

import asyncio
import contextlib

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup

from src.core.logging import get_logger

logger = get_logger(__name__)

_FLOOD_MAX_RETRIES = 3


class TelegramMessenger:
    """Thin wrapper around the aiogram Bot for reliable message delivery."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
        parse_mode: str = "HTML",
    ) -> None:
        """Send a message with flood-control retry."""
        await send_message_with_retry(
            self._bot,
            chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )

    async def edit_or_send(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
        parse_mode: str | None = "HTML",
    ) -> None:
        """Edit an existing message or fall back to sending a new one.

        This is the canonical pattern for task completion notifications.
        Use parse_mode=None for plain text (e.g. AI-generated content with <, >, &).
        """
        edit_kwargs: dict = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "reply_markup": reply_markup,
        }
        if parse_mode is not None:
            edit_kwargs["parse_mode"] = parse_mode
        try:
            await self._bot.edit_message_text(**edit_kwargs)
        except (TelegramBadRequest, Exception) as edit_exc:
            logger.warning(
                "edit_message_text failed, falling back to send_message",
                error=str(edit_exc),
                chat_id=chat_id,
                message_id=message_id,
            )
            await send_message_with_retry(
                self._bot,
                chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
            with contextlib.suppress(Exception):
                await self._bot.delete_message(chat_id=chat_id, message_id=message_id)


async def send_message_with_retry(
    bot: Bot,
    chat_id: int,
    *,
    text: str,
    parse_mode: str | None = "HTML",
    reply_markup: InlineKeyboardMarkup | None = None,
    **kwargs,
) -> None:
    """Send a Telegram message with flood-control aware retry.

    Retries up to ``_FLOOD_MAX_RETRIES`` times on ``TelegramRetryAfter``.
    Raises on the final failure.
    """
    send_kwargs: dict = {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": reply_markup,
        **kwargs,
    }
    if parse_mode is not None:
        send_kwargs["parse_mode"] = parse_mode
    for attempt in range(_FLOOD_MAX_RETRIES):
        try:
            await bot.send_message(**send_kwargs)
            return
        except TelegramBadRequest as exc:
            logger.error(
                "send_message BadRequest",
                error=str(exc),
                chat_id=chat_id,
                text_len=len(text),
                text_preview=text[:100] if text else "",
            )
            raise
        except TelegramRetryAfter as exc:
            if attempt == _FLOOD_MAX_RETRIES - 1:
                raise
            logger.warning("send_message flood control, pausing", retry_after=exc.retry_after)
            await asyncio.sleep(exc.retry_after)
