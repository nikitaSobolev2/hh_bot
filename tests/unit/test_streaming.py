from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramRetryAfter

from src.services.ai.streaming import (
    _build_final_text,
    _truncate,
    stream_to_telegram,
)


async def _async_gen(*chunks: str):
    for chunk in chunks:
        yield chunk


def _make_bot() -> AsyncMock:
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    bot.send_message_draft = AsyncMock()
    return bot


class TestStreamToTelegram:
    @pytest.mark.asyncio
    async def test_empty_stream_returns_empty_string(self):
        bot = _make_bot()
        result = await stream_to_telegram(bot, 123, _async_gen())

        assert result == ""
        bot.send_message.assert_not_called()
        bot.send_message_draft.assert_not_called()

    @pytest.mark.asyncio
    async def test_single_chunk_sends_complete_message(self):
        bot = _make_bot()
        result = await stream_to_telegram(
            bot,
            123,
            _async_gen("full response"),
            initial_text="Header: ",
        )

        assert result == "full response"
        bot.send_message.assert_awaited_once()
        call_kwargs = bot.send_message.call_args.kwargs
        assert "full response" in call_kwargs["text"]
        assert "Header: " in call_kwargs["text"] or "Header" in call_kwargs["text"]
        bot.send_message_draft.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_chunks_streams_via_drafts(self):
        bot = _make_bot()

        with patch("src.services.ai.streaming.time") as mock_time:
            call_count = 0

            def advancing_monotonic():
                nonlocal call_count
                call_count += 1
                return call_count * 1.0

            mock_time.monotonic = advancing_monotonic

            result = await stream_to_telegram(
                bot,
                123,
                _async_gen("chunk1", "chunk2", "chunk3"),
            )

        assert result == "chunk1chunk2chunk3"
        assert bot.send_message_draft.await_count > 0
        bot.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_final_message_contains_all_chunks(self):
        bot = _make_bot()

        with patch("src.services.ai.streaming.time") as mock_time:
            mock_time.monotonic = MagicMock(side_effect=[float(i) for i in range(20)])

            await stream_to_telegram(
                bot,
                123,
                _async_gen("aaa", "bbb", "ccc"),
                initial_text="H: ",
            )

        final_call = bot.send_message.call_args.kwargs
        assert "aaabbbccc" in final_call["text"]

    @pytest.mark.asyncio
    async def test_single_chunk_no_drafts_sent(self):
        bot = _make_bot()
        await stream_to_telegram(bot, 123, _async_gen("only one"))

        bot.send_message_draft.assert_not_called()
        bot.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_draft_flood_control_sleeps_and_continues(self):
        bot = _make_bot()
        retry_exc = TelegramRetryAfter(
            method=MagicMock(),
            message="Flood control",
            retry_after=2,
        )
        bot.send_message_draft.side_effect = [retry_exc, None, None]

        with patch("src.services.ai.streaming.time") as mock_time:
            mock_time.monotonic = MagicMock(side_effect=[float(i) for i in range(20)])
            with patch("src.services.ai.streaming.asyncio.sleep", new_callable=AsyncMock):
                result = await stream_to_telegram(
                    bot,
                    123,
                    _async_gen("a", "b", "c"),
                )

        assert result == "abc"

    @pytest.mark.asyncio
    async def test_header_hourglass_replaced_with_checkmark(self):
        bot = _make_bot()
        await stream_to_telegram(
            bot,
            123,
            _async_gen("done"),
            initial_text="\u23f3 Generating...",
        )

        final_text = bot.send_message.call_args.kwargs["text"]
        assert "\u23f3" not in final_text
        assert "\u2705" in final_text
        assert "..." not in final_text

    @pytest.mark.asyncio
    async def test_parse_mode_forwarded(self):
        bot = _make_bot()
        await stream_to_telegram(
            bot,
            42,
            _async_gen("text"),
            parse_mode="HTML",
        )

        call_kwargs = bot.send_message.call_args.kwargs
        assert call_kwargs["parse_mode"] == "HTML"


class TestBuildFinalText:
    def test_replaces_hourglass_with_checkmark(self):
        result = _build_final_text("\u23f3 Loading...", "content")
        assert "\u2705" in result
        assert "\u23f3" not in result
        assert "..." not in result
        assert "content" in result

    def test_plain_header_unchanged(self):
        result = _build_final_text("Title: ", "body")
        assert result == "Title: body"


class TestTruncate:
    def test_short_text_unchanged(self):
        assert _truncate("short") == "short"

    def test_long_text_truncated_from_end(self):
        long_text = "x" * 5000
        result = _truncate(long_text)
        assert len(result) == 4000
        assert result == long_text[-4000:]
