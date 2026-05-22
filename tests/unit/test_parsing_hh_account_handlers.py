"""Unit tests for parsing HH account selection in the new-parsing FSM."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.i18n import I18nContext


def _make_i18n() -> I18nContext:
    return I18nContext(locale="en")


def _make_user(user_id: int = 42) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    return user


def _make_message() -> AsyncMock:
    message = AsyncMock()
    message.text = "python"
    message.answer = AsyncMock()
    return message


def _make_callback() -> AsyncMock:
    callback = AsyncMock()
    callback.message = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    return callback


def _make_state(data: dict | None = None) -> AsyncMock:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value=data or {})
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    return state


class TestParsingHhAccountSetup:
    @pytest.mark.asyncio
    async def test_keyword_filter_without_resume_skips_account_step(self):
        from src.bot.modules.parsing.handlers import fsm_keyword_filter

        message = _make_message()
        state = _make_state()

        with patch(
            "src.bot.modules.parsing.handlers._continue_parsing_hh_account_setup",
            new_callable=AsyncMock,
        ) as continue_setup:
            await fsm_keyword_filter(message, _make_user(), state, _make_i18n())

        state.update_data.assert_awaited_once_with(keyword_filter="python")
        continue_setup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_continue_setup_without_resume_goes_to_target_count(self):
        from src.bot.modules.parsing.handlers import _continue_parsing_hh_account_setup

        message = _make_message()
        state = _make_state(
            {"search_url": "https://hh.ru/search/vacancy?text=python", "keyword_filter": "python"}
        )

        with patch(
            "src.bot.modules.parsing.handlers._proceed_to_target_count",
            new_callable=AsyncMock,
        ) as proceed:
            await _continue_parsing_hh_account_setup(
                message,
                state=state,
                user=_make_user(),
                session=AsyncMock(),
                i18n=_make_i18n(),
            )

        state.update_data.assert_awaited_with(parse_hh_linked_account_id=None)
        proceed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_continue_setup_auto_picks_single_ready_account(self):
        from src.bot.modules.parsing.handlers import _continue_parsing_hh_account_setup

        message = _make_message()
        state = _make_state(
            {
                "search_url": "https://hh.ru/search/vacancy?text=python&resume=abc",
                "keyword_filter": "python",
            }
        )
        ready_account = MagicMock(id=3, browser_storage_enc=b"x")

        with (
            patch(
                "src.bot.modules.parsing.handlers.HhLinkedAccountRepository"
            ) as repo_cls,
            patch(
                "src.bot.modules.parsing.handlers._proceed_to_target_count",
                new_callable=AsyncMock,
            ) as proceed,
        ):
            repo = repo_cls.return_value
            repo.list_active_for_user = AsyncMock(return_value=[ready_account])
            await _continue_parsing_hh_account_setup(
                message,
                state=state,
                user=_make_user(),
                session=AsyncMock(),
                i18n=_make_i18n(),
            )

        state.update_data.assert_awaited_with(parse_hh_linked_account_id=3)
        proceed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_hh_account_skip_clears_account_and_proceeds(self):
        from src.bot.modules.parsing.handlers import parsing_hh_account_skip

        callback = _make_callback()
        state = _make_state()
        i18n = _make_i18n()

        with patch(
            "src.bot.modules.parsing.handlers._proceed_to_target_count",
            new_callable=AsyncMock,
        ) as proceed:
            await parsing_hh_account_skip(callback, state, i18n)

        state.update_data.assert_awaited_once_with(parse_hh_linked_account_id=None)
        proceed.assert_awaited_once_with(callback, state, i18n)

    @pytest.mark.asyncio
    async def test_hh_account_pick_ready_account_proceeds(self):
        from src.bot.modules.parsing.handlers import parsing_hh_account_pick

        callback = _make_callback()
        state = _make_state()
        acc = MagicMock(id=5, user_id=42, browser_storage_enc=b"x", label="Main")

        with (
            patch(
                "src.bot.modules.parsing.handlers.HhLinkedAccountRepository"
            ) as repo_cls,
            patch(
                "src.bot.modules.parsing.handlers._proceed_to_target_count",
                new_callable=AsyncMock,
            ) as proceed,
        ):
            repo = repo_cls.return_value
            repo.get_by_id = AsyncMock(return_value=acc)
            await parsing_hh_account_pick(
                callback,
                MagicMock(aux_id=5),
                state,
                _make_user(),
                AsyncMock(),
                _make_i18n(),
            )

        state.update_data.assert_awaited_once_with(
            parse_hh_linked_account_id=5,
            parsing_selected_hh_account_id=5,
        )
        proceed.assert_awaited_once()
