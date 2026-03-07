"""Telegram message streaming via sendMessageDraft (Bot API 9.5+).

Falls back to progressive edit_message_text when draft streaming is unavailable.
"""

import asyncio
import contextlib
import random
import time
from collections.abc import AsyncGenerator

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from src.core.logging import get_logger

logger = get_logger(__name__)

_EDIT_INTERVAL_MS = 500
_EDIT_TOKEN_BATCH = 15
_DRAFT_INTERVAL_MS = 120
_DRAFT_TOKEN_BATCH = 6


async def stream_to_telegram(
    bot: Bot,
    chat_id: int,
    token_stream: AsyncGenerator[str, None],
    *,
    initial_text: str = "",
    parse_mode: str | None = None,
    use_drafts: bool = True,
) -> str:
    """Stream AI tokens to a Telegram chat.

    Uses ``sendMessageDraft`` for native animated streaming when *use_drafts*
    is True, otherwise falls back to repeated ``editMessageText`` calls.

    Returns the accumulated AI-generated text (without *initial_text*).
    """
    if use_drafts:
        return await _stream_via_drafts(
            bot,
            chat_id,
            token_stream,
            initial_text=initial_text,
            parse_mode=parse_mode,
        )
    return await _stream_via_edits(
        bot,
        chat_id,
        token_stream,
        initial_text=initial_text,
        parse_mode=parse_mode,
    )


async def _stream_via_drafts(
    bot: Bot,
    chat_id: int,
    token_stream: AsyncGenerator[str, None],
    *,
    initial_text: str,
    parse_mode: str | None,
) -> str:
    draft_id = random.randint(1, 2**31 - 1)

    accumulated = ""
    token_buffer = ""
    last_send_time = time.monotonic()
    draft_calls = 0

    async for chunk in token_stream:
        token_buffer += chunk
        accumulated += chunk

        now = time.monotonic()
        elapsed_ms = (now - last_send_time) * 1000
        should_send = len(token_buffer) >= _DRAFT_TOKEN_BATCH or elapsed_ms >= _DRAFT_INTERVAL_MS

        if should_send:
            display_text = initial_text + accumulated + " \u258c"
            if len(display_text) > 4096:
                display_text = display_text[-4000:]

            try:
                await bot.send_message_draft(
                    chat_id=chat_id,
                    draft_id=draft_id,
                    text=display_text,
                    parse_mode=parse_mode,
                )
                draft_calls += 1
            except TelegramBadRequest as exc:
                logger.warning("sendMessageDraft failed", error=str(exc))

            token_buffer = ""
            last_send_time = time.monotonic()

    final_text = initial_text.replace("\u23f3", "\u2705").replace("...", "") + accumulated
    if len(final_text) > 4096:
        final_text = final_text[-4000:]

    await bot.send_message(chat_id=chat_id, text=final_text, parse_mode=parse_mode)

    logger.info("Draft streaming complete", draft_calls=draft_calls, chars=len(accumulated))
    return accumulated


async def _stream_via_edits(
    bot: Bot,
    chat_id: int,
    token_stream: AsyncGenerator[str, None],
    *,
    initial_text: str,
    parse_mode: str | None,
) -> str:
    sent_message = await bot.send_message(
        chat_id,
        initial_text or "\u23f3",
        parse_mode=parse_mode,
    )
    message_id = sent_message.message_id

    accumulated = ""
    token_buffer = ""
    last_edit_time = time.monotonic()
    edit_count = 0

    async for chunk in token_stream:
        token_buffer += chunk
        accumulated += chunk

        now = time.monotonic()
        elapsed_ms = (now - last_edit_time) * 1000
        should_edit = len(token_buffer) >= _EDIT_TOKEN_BATCH or elapsed_ms >= _EDIT_INTERVAL_MS

        if should_edit:
            display_text = initial_text + accumulated + " \u258c"
            if len(display_text) > 4000:
                display_text = display_text[-3900:]

            try:
                await bot.edit_message_text(
                    text=display_text,
                    chat_id=chat_id,
                    message_id=message_id,
                    parse_mode=parse_mode,
                )
                edit_count += 1
            except TelegramBadRequest:
                pass

            token_buffer = ""
            last_edit_time = time.monotonic()

            if edit_count % 10 == 0:
                await asyncio.sleep(0.1)

    final_text = initial_text.replace("\u23f3", "\u2705").replace("...", "") + accumulated
    if len(final_text) > 4000:
        final_text = final_text[-3950:]

    with contextlib.suppress(TelegramBadRequest):
        await bot.edit_message_text(
            text=final_text,
            chat_id=chat_id,
            message_id=message_id,
            parse_mode=parse_mode,
        )

    logger.info("Edit streaming complete", edits=edit_count, chars=len(accumulated))
    return accumulated
