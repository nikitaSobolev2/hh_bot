"""Telegram message streaming via sendMessageDraft (Bot API 9.5+).

Sends a complete message when the OpenAI response arrives in a single chunk.
Streams progressively via drafts when the response arrives in multiple chunks.
"""

import asyncio
import random
import time
from collections.abc import AsyncGenerator

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

from src.core.logging import get_logger

logger = get_logger(__name__)

_DRAFT_INTERVAL_MS = 500
_FLOOD_MAX_RETRIES = 3
_MAX_MESSAGE_LENGTH = 4096
_TRUNCATED_LENGTH = 4000


async def stream_to_telegram(
    bot: Bot,
    chat_id: int,
    token_stream: AsyncGenerator[str, None],
    *,
    initial_text: str = "",
    parse_mode: str | None = None,
) -> str:
    """Stream an OpenAI response to a Telegram chat.

    If the response arrives as a single chunk, sends it as a complete message.
    If multiple chunks arrive, streams progressively via ``sendMessageDraft``.

    Returns the accumulated AI-generated text (without *initial_text*).
    """
    first_chunk = await anext(token_stream, None)
    if not first_chunk:
        return ""

    second_chunk = await anext(token_stream, None)
    if not second_chunk:
        await _send_complete_response(bot, chat_id, initial_text, first_chunk, parse_mode)
        return first_chunk

    remaining = _prepend_chunks([first_chunk, second_chunk], token_stream)
    return await _stream_via_drafts(bot, chat_id, remaining, initial_text, parse_mode)


async def _send_complete_response(
    bot: Bot,
    chat_id: int,
    header: str,
    content: str,
    parse_mode: str | None,
) -> None:
    text = _build_final_text(header, content)
    await _send_with_retry(bot, chat_id, text=text, parse_mode=parse_mode)


async def _stream_via_drafts(
    bot: Bot,
    chat_id: int,
    token_stream: AsyncGenerator[str, None],
    initial_text: str,
    parse_mode: str | None,
) -> str:
    draft_id = random.randint(1, 2**31 - 1)
    accumulated = ""
    last_update = time.monotonic()
    draft_calls = 0

    async for chunk in token_stream:
        accumulated += chunk

        if not _should_update_draft(last_update):
            continue

        await _update_draft(bot, chat_id, draft_id, initial_text + accumulated, parse_mode)
        draft_calls += 1
        last_update = time.monotonic()

    final_text = _build_final_text(initial_text, accumulated)
    await _send_with_retry(bot, chat_id, text=final_text, parse_mode=parse_mode)

    logger.info("Draft streaming complete", draft_calls=draft_calls, chars=len(accumulated))
    return accumulated


def _should_update_draft(last_update: float) -> bool:
    elapsed_ms = (time.monotonic() - last_update) * 1000
    return elapsed_ms >= _DRAFT_INTERVAL_MS


async def _update_draft(
    bot: Bot,
    chat_id: int,
    draft_id: int,
    text: str,
    parse_mode: str | None,
) -> None:
    display = _truncate(text + " \u258c")
    try:
        await bot.send_message_draft(
            chat_id=chat_id,
            draft_id=draft_id,
            text=display,
            parse_mode=parse_mode,
        )
    except TelegramRetryAfter as exc:
        logger.warning("Draft flood control, pausing", retry_after=exc.retry_after)
        await asyncio.sleep(exc.retry_after)
    except TelegramBadRequest as exc:
        logger.warning("sendMessageDraft failed", error=str(exc))


def _build_final_text(header: str, content: str) -> str:
    clean_header = header.replace("\u23f3", "\u2705").replace("...", "")
    return _truncate(clean_header + content)


def _truncate(text: str) -> str:
    if len(text) > _MAX_MESSAGE_LENGTH:
        return text[-_TRUNCATED_LENGTH:]
    return text


async def _prepend_chunks(
    buffered: list[str],
    remaining: AsyncGenerator[str, None],
) -> AsyncGenerator[str, None]:
    for chunk in buffered:
        yield chunk
    async for chunk in remaining:
        yield chunk


async def _send_with_retry(
    bot: Bot,
    chat_id: int,
    *,
    text: str,
    parse_mode: str | None = None,
    **kwargs,
) -> None:
    for attempt in range(_FLOOD_MAX_RETRIES):
        try:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode, **kwargs)
            return
        except TelegramRetryAfter as exc:
            if attempt == _FLOOD_MAX_RETRIES - 1:
                raise
            logger.warning("send_message flood control, pausing", retry_after=exc.retry_after)
            await asyncio.sleep(exc.retry_after)
