"""Tests for src.services.bot_pin_cleanup."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Chat, Message, User

from src.services.bot_pin_cleanup import clear_bot_pinned_messages_top_stack

BOT_ID = 999001
CHAT_ID = 111222333


def _bot_message(message_id: int, *, from_bot_id: int = BOT_ID) -> Message:
    return Message(
        message_id=message_id,
        date=datetime.now(UTC),
        chat=Chat(id=CHAT_ID, type="private"),
        from_user=User(id=from_bot_id, is_bot=True, first_name="Bot"),
        text="progress",
    )


def _user_message(message_id: int, *, uid: int = 42) -> Message:
    return Message(
        message_id=message_id,
        date=datetime.now(UTC),
        chat=Chat(id=CHAT_ID, type="private"),
        from_user=User(id=uid, is_bot=False, first_name="Human"),
        text="mine",
    )


def _chat_with_pin(pinned: Message | None) -> MagicMock:
    c = MagicMock()
    c.pinned_message = pinned
    return c


@pytest.mark.asyncio
async def test_unpins_sequential_bot_pins_until_none():
    """Top pin visible each time: two bot pins then clear."""
    bot = MagicMock()
    bot.get_chat = AsyncMock(
        side_effect=[
            _chat_with_pin(_bot_message(50)),
            _chat_with_pin(_bot_message(49)),
            _chat_with_pin(None),
        ]
    )
    bot.unpin_chat_message = AsyncMock()

    n = await clear_bot_pinned_messages_top_stack(bot, [CHAT_ID], bot_id=BOT_ID)

    assert n == 2
    assert bot.unpin_chat_message.await_count == 2
    bot.unpin_chat_message.assert_any_await(CHAT_ID, message_id=50)
    bot.unpin_chat_message.assert_any_await(CHAT_ID, message_id=49)


@pytest.mark.asyncio
async def test_stops_when_top_pin_is_from_user():
    bot = MagicMock()
    bot.get_chat = AsyncMock(side_effect=[_chat_with_pin(_user_message(10))])
    bot.unpin_chat_message = AsyncMock()

    n = await clear_bot_pinned_messages_top_stack(bot, [CHAT_ID], bot_id=BOT_ID)

    assert n == 0
    bot.unpin_chat_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_skips_non_dm_chat_ids():
    bot = MagicMock()
    bot.get_chat = AsyncMock()
    bot.unpin_chat_message = AsyncMock()

    n = await clear_bot_pinned_messages_top_stack(bot, [-100123, 0], bot_id=BOT_ID)

    assert n == 0
    bot.get_chat.assert_not_awaited()
