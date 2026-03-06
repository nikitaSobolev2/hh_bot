"""Integration tests for bot handlers using mocked Telegram updates."""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestStartHandler:
    @pytest.mark.asyncio
    async def test_start_command_sends_welcome(self):
        from src.bot.modules.start.handlers import cmd_start

        message = AsyncMock()
        user = MagicMock()
        user.is_admin = False

        await cmd_start(message, user)

        message.answer.assert_called_once()
        call_args = message.answer.call_args
        assert "HH Bot" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_start_command_shows_admin_kb_for_admin(self):
        from src.bot.modules.start.handlers import cmd_start

        message = AsyncMock()
        user = MagicMock()
        user.is_admin = True

        await cmd_start(message, user)

        call_args = message.answer.call_args
        kb = call_args.kwargs.get("reply_markup")
        assert kb is not None
        buttons_text = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("Admin" in t for t in buttons_text)

    @pytest.mark.asyncio
    async def test_start_command_hides_admin_for_regular_user(self):
        from src.bot.modules.start.handlers import cmd_start

        message = AsyncMock()
        user = MagicMock()
        user.is_admin = False

        await cmd_start(message, user)

        call_args = message.answer.call_args
        kb = call_args.kwargs.get("reply_markup")
        buttons_text = [btn.text for row in kb.inline_keyboard for btn in row]
        assert not any("Admin" in t for t in buttons_text)


class TestProfileHandler:
    @pytest.mark.asyncio
    async def test_show_profile_displays_user_info(self):
        from src.bot.modules.profile.handlers import show_profile

        callback = AsyncMock()
        callback.message = AsyncMock()

        user = MagicMock()
        user.first_name = "John"
        user.last_name = "Doe"
        user.username = "johndoe"
        user.role.name = "user"
        user.balance = 100
        user.language_code = "en"
        user.created_at.strftime.return_value = "2024-01-01"

        await show_profile(callback, user)

        call_args = callback.message.edit_text.call_args
        text = call_args.args[0]
        assert "John" in text
        assert "johndoe" in text
