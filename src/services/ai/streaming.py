"""Telegram message streaming — progressively edits a message as AI generates tokens."""

import asyncio
import contextlib
import time

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from src.core.logging import get_logger
from src.services.ai.client import AIClient

logger = get_logger(__name__)

MIN_EDIT_INTERVAL_MS = 500
TOKEN_BATCH_SIZE = 15


async def stream_to_telegram(
    bot: Bot,
    chat_id: int,
    ai_client: AIClient,
    resume_title: str,
    keywords: list[str],
    style: str,
    *,
    initial_text: str = "⏳ Generating key phrases...\n\n",
) -> str:
    """Stream AI output by progressively editing a Telegram message.

    Returns the final complete text.
    """
    sent_message = await bot.send_message(chat_id, initial_text)
    message_id = sent_message.message_id

    accumulated = ""
    token_buffer = ""
    last_edit_time = time.monotonic()
    edit_count = 0

    async for chunk in ai_client.stream_key_phrases(resume_title, keywords, style):
        token_buffer += chunk
        accumulated += chunk

        now = time.monotonic()
        elapsed_ms = (now - last_edit_time) * 1000
        should_edit = len(token_buffer) >= TOKEN_BATCH_SIZE or elapsed_ms >= MIN_EDIT_INTERVAL_MS

        if should_edit:
            display_text = initial_text + accumulated + " ▌"
            if len(display_text) > 4000:
                display_text = display_text[-3900:]

            try:
                await bot.edit_message_text(
                    text=display_text,
                    chat_id=chat_id,
                    message_id=message_id,
                )
                edit_count += 1
            except TelegramBadRequest:
                pass

            token_buffer = ""
            last_edit_time = time.monotonic()

            if edit_count % 10 == 0:
                await asyncio.sleep(0.1)

    final_text = initial_text.replace("⏳", "✅").replace("...", "") + accumulated
    if len(final_text) > 4000:
        final_text = final_text[-3950:]

    with contextlib.suppress(TelegramBadRequest):
        await bot.edit_message_text(
            text=final_text,
            chat_id=chat_id,
            message_id=message_id,
        )

    logger.info("Streaming complete", edits=edit_count, chars=len(accumulated))
    return accumulated
