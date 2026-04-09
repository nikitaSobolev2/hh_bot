"""Unit tests for progress bar cancel handler."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.i18n import I18nContext


def _make_i18n() -> I18nContext:
    return I18nContext(locale="en")


def _make_user(telegram_id: int = 12345) -> MagicMock:
    user = MagicMock()
    user.telegram_id = telegram_id
    user.language_code = "en"
    return user


def _make_callback(
    data: str = "prog:cancel:parse_1",
    chat_id: int = 12345,
) -> AsyncMock:
    callback = AsyncMock()
    callback.data = data
    callback.message = MagicMock()
    callback.message.chat.id = chat_id
    bot = MagicMock()
    bot.unpin_chat_message = AsyncMock()
    bot.delete_message = AsyncMock()
    bot.edit_message_text = AsyncMock()
    callback.bot = bot
    return callback


class TestHandleProgressCancel:
    @pytest.mark.asyncio
    async def test_returns_early_when_chat_id_mismatch(self):
        from src.bot.modules.progress.handlers import handle_progress_cancel

        callback = _make_callback(chat_id=99999)
        user = _make_user(telegram_id=12345)

        await handle_progress_cancel(callback, user, _make_i18n())

        callback.answer.assert_awaited_once()
        callback.answer.assert_awaited_with()

    @pytest.mark.asyncio
    async def test_returns_early_when_task_key_invalid(self):
        from src.bot.modules.progress.handlers import handle_progress_cancel

        callback = _make_callback(data="prog:cancel:")
        user = _make_user(telegram_id=12345)

        await handle_progress_cancel(callback, user, _make_i18n())

        callback.answer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_answers_already_finished_when_task_missing_from_redis(self):
        from src.bot.modules.progress.handlers import handle_progress_cancel

        callback = _make_callback()
        user = _make_user(telegram_id=12345)

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.aclose = AsyncMock()

        with patch(
            "src.bot.modules.progress.handlers.create_progress_redis",
            return_value=redis,
        ):
            await handle_progress_cancel(callback, user, _make_i18n())

        callback.answer.assert_awaited_once()
        callback.answer.assert_awaited_with(
            "Task already finished.",
            show_alert=True,
        )

    @pytest.mark.asyncio
    async def test_cancels_task_when_state_has_no_celery_task_id(self):
        from src.bot.modules.progress.handlers import handle_progress_cancel

        callback = _make_callback(data="prog:cancel:parse_1")
        user = _make_user(telegram_id=12345)

        state = {"title": "Test", "status": "running", "bars": [], "celery_task_id": None}
        redis = AsyncMock()
        def mock_get(key: str):
            if "progress:pin:" in key:
                return "42"
            if "progress:task:12345:parse:1" in key:
                return json.dumps(state)
            return None

        redis.get = AsyncMock(side_effect=mock_get)
        redis.delete = AsyncMock()
        redis.keys = AsyncMock(return_value=[])
        redis.mget = AsyncMock(return_value=[])
        redis.aclose = AsyncMock()

        with (
            patch(
                "src.bot.modules.progress.handlers.create_progress_redis",
                return_value=redis,
            ),
            patch(
                "src.bot.modules.progress.handlers.get_hh_ui_batch_active_sync",
                return_value=None,
            ),
            patch(
                "src.bot.modules.progress.handlers.load_hh_ui_batch_checkpoint_full_sync",
                return_value=None,
            ),
            patch(
                "src.bot.modules.progress.handlers.load_autorespond_ui_tail_sync",
                return_value=[],
            ),
            patch(
                "src.bot.modules.progress.handlers.set_user_cancelled_sync",
            ),
        ):
            await handle_progress_cancel(callback, user, _make_i18n())

        callback.answer.assert_awaited_with(
            "Task cancelled.",
            show_alert=True,
        )

    @pytest.mark.asyncio
    async def test_cancels_autorespond_without_celery_task_id(self):
        from src.bot.modules.progress.handlers import handle_progress_cancel

        callback = _make_callback(data="prog:cancel:autorespond_1_old")
        user = _make_user(telegram_id=12345)

        state = {"title": "Test", "status": "running", "bars": [], "celery_task_id": None}
        redis = AsyncMock()

        def mock_get(key: str):
            if "progress:pin:" in key:
                return "42"
            if "progress:task:12345:" in key:
                return json.dumps(state)
            return None

        redis.get = AsyncMock(side_effect=mock_get)
        redis.delete = AsyncMock()
        redis.keys = AsyncMock(return_value=[])
        redis.mget = AsyncMock(return_value=[])
        redis.aclose = AsyncMock()

        with (
            patch(
                "src.bot.modules.progress.handlers.create_progress_redis",
                return_value=redis,
            ),
            patch(
                "src.bot.modules.progress.handlers.get_hh_ui_batch_active_sync",
                return_value=None,
            ),
            patch(
                "src.bot.modules.progress.handlers.load_hh_ui_batch_checkpoint_full_sync",
                return_value=None,
            ),
            patch(
                "src.bot.modules.progress.handlers.load_autorespond_ui_tail_sync",
                return_value=[],
            ),
            patch(
                "src.bot.modules.progress.handlers.clear_hh_ui_batch_checkpoint_sync",
            ),
            patch(
                "src.bot.modules.progress.handlers.clear_hh_ui_resume_envelope_sync",
            ),
            patch(
                "src.bot.modules.progress.handlers.clear_autorespond_ui_tail_sync",
            ),
            patch(
                "src.bot.modules.progress.handlers.set_autorespond_cancelled",
                new_callable=AsyncMock,
            ) as mock_cancel,
            patch(
                "src.bot.modules.progress.handlers.clear_autorespond_done_counter",
                new_callable=AsyncMock,
            ),
            patch(
                "src.bot.modules.progress.handlers.clear_autorespond_failed_counter",
                new_callable=AsyncMock,
            ),
            patch(
                "src.bot.modules.progress.handlers.set_user_cancelled_sync",
            ),
        ):
            await handle_progress_cancel(callback, user, _make_i18n())

        mock_cancel.assert_awaited_once()
        callback.answer.assert_awaited_with(
            "Task cancelled.",
            show_alert=True,
        )

    @pytest.mark.asyncio
    async def test_revokes_task_and_cancels_when_valid(self):
        from src.bot.modules.progress.handlers import handle_progress_cancel

        callback = _make_callback()
        user = _make_user(telegram_id=12345)

        state = {
            "title": "Test",
            "status": "running",
            "bars": [],
            "celery_task_id": "celery-task-123",
        }

        def mock_get(key: str):
            if "progress:pin:" in key:
                return "42"
            if "progress:task:12345:parse:1" in key:
                return json.dumps(state)
            return None

        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=mock_get)
        redis.delete = AsyncMock()
        redis.keys = AsyncMock(return_value=[])
        redis.mget = AsyncMock(return_value=[])
        redis.aclose = AsyncMock()

        with (
            patch(
                "src.bot.modules.progress.handlers.create_progress_redis",
                return_value=redis,
            ),
            patch(
                "src.bot.modules.progress.handlers.get_hh_ui_batch_active_sync",
                return_value=None,
            ),
            patch(
                "src.bot.modules.progress.handlers.load_hh_ui_batch_checkpoint_full_sync",
                return_value=None,
            ),
            patch(
                "src.bot.modules.progress.handlers.load_autorespond_ui_tail_sync",
                return_value=[],
            ),
            patch(
                "src.bot.modules.progress.handlers.set_user_cancelled_sync",
            ),
            patch(
                "src.bot.modules.progress.handlers.run_sync_in_thread",
                new_callable=AsyncMock,
            ) as mock_revoke,
        ):
            await handle_progress_cancel(callback, user, _make_i18n())

        mock_revoke.assert_awaited_once()
        call_args = mock_revoke.call_args
        assert call_args.args[1] == "celery-task-123"
        assert call_args.kwargs["terminate"] is True
        callback.answer.assert_awaited_with(
            "Task cancelled.",
            show_alert=True,
        )

    @pytest.mark.asyncio
    async def test_cancels_task_group_with_active_hh_ui_child(self):
        from src.bot.modules.progress.handlers import handle_progress_cancel

        callback = _make_callback(data="prog:cancel:taskgroup_1")
        user = _make_user(telegram_id=12345)

        state = {"title": "Group", "status": "running", "bars": [], "celery_task_id": None}

        def mock_get(key: str):
            if "progress:pin:" in key:
                return "42"
            if "progress:task:12345:taskgroup:1" in key:
                return json.dumps(state)
            return None

        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=mock_get)
        redis.delete = AsyncMock()
        redis.keys = AsyncMock(return_value=[])
        redis.mget = AsyncMock(return_value=[])
        redis.aclose = AsyncMock()

        with (
            patch(
                "src.bot.modules.progress.handlers.create_progress_redis",
                return_value=redis,
            ),
            patch(
                "src.bot.modules.progress.handlers.get_hh_ui_batch_active_sync",
                return_value="hh-ui-child-1",
            ),
            patch(
                "src.bot.modules.progress.handlers.load_hh_ui_batch_checkpoint_full_sync",
                return_value=None,
            ),
            patch(
                "src.bot.modules.progress.handlers.load_autorespond_ui_tail_sync",
                return_value=[],
            ),
            patch(
                "src.bot.modules.progress.handlers.set_autorespond_cancelled",
                new_callable=AsyncMock,
            ) as mock_cancel,
            patch(
                "src.bot.modules.progress.handlers.clear_autorespond_done_counter",
                new_callable=AsyncMock,
            ),
            patch(
                "src.bot.modules.progress.handlers.clear_autorespond_failed_counter",
                new_callable=AsyncMock,
            ),
            patch(
                "src.bot.modules.progress.handlers.clear_hh_ui_batch_checkpoint_sync",
            ),
            patch(
                "src.bot.modules.progress.handlers.clear_hh_ui_resume_envelope_sync",
            ),
            patch(
                "src.bot.modules.progress.handlers.clear_autorespond_ui_tail_sync",
            ),
            patch(
                "src.bot.modules.progress.handlers.clear_hh_ui_batch_active_sync",
            ),
            patch(
                "src.bot.modules.progress.handlers.set_user_cancelled_sync",
            ),
            patch(
                "src.bot.modules.progress.handlers.run_sync_in_thread",
                new_callable=AsyncMock,
            ) as mock_revoke,
        ):
            await handle_progress_cancel(callback, user, _make_i18n())

        mock_cancel.assert_awaited_once_with(12345, "taskgroup:1")
        mock_revoke.assert_awaited_once()
        assert mock_revoke.call_args.args[1] == "hh-ui-child-1"
        callback.answer.assert_awaited_with(
            "Task cancelled.",
            show_alert=True,
        )
