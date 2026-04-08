"""Remove bot-sent pins on startup (private chats only).

Telegram Bot API exposes only the *most recent* pinned message per chat via
``get_chat``. We repeatedly unpin while the top pin is from the bot. If a user
pin sits above bot pins, lower bot pins are not visible and cannot be cleared
until that user pin is removed — an API limitation, not a bug in the loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

from sqlalchemy import select

from src.core.logging import get_logger
from src.db.engine import async_session_factory
from src.models.user import User
from src.services.progress_service import create_progress_redis, scan_progress_namespace_chat_ids

logger = get_logger(__name__)


async def load_startup_pin_cleanup_chat_ids() -> set[int]:
    """Union of all user DM chat IDs (DB) and Redis progress namespace chat IDs."""
    ids: set[int] = set()

    redis = create_progress_redis()
    try:
        ids |= await scan_progress_namespace_chat_ids(redis)
    finally:
        await redis.aclose()

    async with async_session_factory() as session:
        result = await session.execute(select(User.telegram_id))
        ids.update(row[0] for row in result.all())

    return ids


def _pinned_message_from_bot(pinned, bot_id: int) -> bool:
    """True if ``pinned`` is a normal message sent by the bot."""
    from aiogram.types import Message

    if not isinstance(pinned, Message):
        return False
    u = pinned.from_user
    return u is not None and u.id == bot_id


async def _get_chat_retry(bot, chat_id: int):
    """Return chat or ``None`` if the chat cannot be loaded."""
    from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

    while True:
        try:
            return await bot.get_chat(chat_id)
        except TelegramBadRequest as exc:
            logger.debug(
                "startup_pin_cleanup_get_chat_skipped",
                chat_id=chat_id,
                detail=str(exc)[:200],
            )
            return None
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)


async def _unpin_message_retry(bot, chat_id: int, message_id: int) -> bool:
    """Unpin one message; ``False`` if Telegram rejected the unpin."""
    from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

    while True:
        try:
            await bot.unpin_chat_message(chat_id, message_id=message_id)
            return True
        except TelegramBadRequest as exc:
            logger.debug(
                "startup_pin_cleanup_unpin_skipped",
                chat_id=chat_id,
                message_id=message_id,
                detail=str(exc)[:200],
            )
            return False
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)


async def _clear_bot_pins_for_private_chat(bot, chat_id: int, bot_id: int) -> int:
    """Unpin visible bot pins until top pin is absent or not from the bot."""
    count = 0
    while True:
        chat = await _get_chat_retry(bot, chat_id)
        if chat is None:
            break
        pm = chat.pinned_message
        if pm is None or not _pinned_message_from_bot(pm, bot_id):
            break
        if not await _unpin_message_retry(bot, chat_id, pm.message_id):
            break
        count += 1
    return count


async def clear_bot_pinned_messages_top_stack(
    bot,
    chat_ids: Iterable[int],
    *,
    bot_id: int,
) -> int:
    """Unpin bot-sent messages visible as the current top pin, per chat. Returns total unpins."""
    total = 0
    for chat_id in sorted(set(chat_ids)):
        if chat_id <= 0:
            continue
        total += await _clear_bot_pins_for_private_chat(bot, chat_id, bot_id)

    if total:
        logger.info("startup_bot_pins_cleared", unpins=total)
    return total


async def run_startup_bot_pin_cleanup(bot, *, bot_id: int) -> int:
    """Load chat IDs and clear bot-only top pin stacks."""
    chat_ids = await load_startup_pin_cleanup_chat_ids()
    return await clear_bot_pinned_messages_top_stack(bot, chat_ids, bot_id=bot_id)
