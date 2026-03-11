"""Tests for src.services.progress_service.ProgressService."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _key_router(*, pin=None, task=None):
    """Return an async callable that routes redis.get by key prefix.

    This is required because ProgressService calls redis.get with different
    key patterns in the same test execution (task key and pin key).
    """

    async def _get(key: str):
        if "progress:pin:" in key:
            return pin
        if "progress:task:" in key:
            return task
        return None

    return _get


def _make_bot(*, send_message_id: int = 42) -> MagicMock:
    bot = MagicMock()
    msg = MagicMock()
    msg.message_id = send_message_id
    bot.send_message = AsyncMock(return_value=msg)
    bot.edit_message_text = AsyncMock()
    bot.pin_chat_message = AsyncMock()
    bot.unpin_chat_message = AsyncMock()
    bot.delete_message = AsyncMock()
    return bot


def _make_redis(*, pin=None, task=None, task_keys=None, task_values=None) -> MagicMock:
    """Return a mock async Redis client with a key-aware get."""
    r = MagicMock()
    r.get = _key_router(pin=pin, task=task)
    r.set = AsyncMock(return_value=True)
    r.keys = AsyncMock(return_value=task_keys or [])
    r.mget = AsyncMock(return_value=task_values or [])
    r.delete = AsyncMock()
    return r


def _make_service(chat_id: int = 100, locale: str = "ru", *, bot=None, redis=None):
    from src.services.progress_service import ProgressService

    if bot is None:
        bot = _make_bot()
    if redis is None:
        redis = _make_redis()
    return ProgressService(bot, chat_id, redis, locale), bot, redis


def _task_state(
    title: str = "Backend Dev",
    status: str = "running",
    bars: list[dict] | None = None,
) -> dict:
    if bars is None:
        bars = [
            {"label": "🌐 Scraping", "current": 0, "total": 0},
            {"label": "🧠 Keywords", "current": 0, "total": 0},
        ]
    return {"title": title, "status": status, "bars": bars}


# ---------------------------------------------------------------------------
# render_bar
# ---------------------------------------------------------------------------


class TestRenderBar:
    def test_zero_total_returns_empty_bar(self):
        from src.services.progress_service import render_bar

        result = render_bar(0, 0)
        assert "0%" in result
        assert "0/0" in result

    def test_half_progress(self):
        from src.services.progress_service import render_bar

        result = render_bar(10, 20)
        assert "50%" in result
        assert "10/20" in result
        assert "\u2588" in result
        assert "\u2591" in result

    def test_full_progress_shows_100(self):
        from src.services.progress_service import render_bar

        result = render_bar(50, 50)
        assert "100%" in result
        assert "50/50" in result

    def test_output_contains_html_code_tag(self):
        from src.services.progress_service import render_bar

        result = render_bar(5, 10)
        assert "<code>" in result
        assert "</code>" in result


# ---------------------------------------------------------------------------
# start_task
# ---------------------------------------------------------------------------


class TestStartTask:
    @pytest.mark.asyncio
    async def test_writes_task_state_to_redis(self):
        svc, bot, redis = _make_service(chat_id=111)
        # No existing pin, no existing tasks.
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(return_value=True)
        redis.keys = AsyncMock(return_value=["progress:task:111:parse:1"])
        redis.mget = AsyncMock(return_value=[json.dumps(_task_state(title="Backend Dev"))])

        await svc.start_task("parse:1", "Backend Dev", ["🌐 Scraping", "🧠 Keywords"])

        # First set call should store the task state JSON.
        first_set_call = redis.set.call_args_list[0]
        key = first_set_call.args[0]
        raw = first_set_call.args[1]
        assert key == "progress:task:111:parse:1"
        state = json.loads(raw)
        assert state["title"] == "Backend Dev"
        assert state["status"] == "running"
        assert len(state["bars"]) == 2

    @pytest.mark.asyncio
    async def test_sends_message_and_pins_in_dm(self):
        svc, bot, redis = _make_service(chat_id=111)
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(return_value=True)
        redis.keys = AsyncMock(return_value=["progress:task:111:parse:1"])
        redis.mget = AsyncMock(return_value=[json.dumps(_task_state())])

        await svc.start_task("parse:1", "Backend Dev", ["🌐 Scraping"])

        bot.send_message.assert_awaited_once()
        bot.pin_chat_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_does_not_pin_in_group_chat(self):
        # Negative chat_id = group chat.
        svc, bot, redis = _make_service(chat_id=-100123)
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(return_value=True)
        redis.keys = AsyncMock(return_value=["progress:task:-100123:parse:1"])
        redis.mget = AsyncMock(return_value=[json.dumps(_task_state())])

        await svc.start_task("parse:1", "Backend Dev", ["🌐 Scraping"])

        bot.send_message.assert_awaited_once()
        bot.pin_chat_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_edits_existing_message_when_pin_present(self):
        svc, bot, redis = _make_service(chat_id=111)
        # Simulate existing pin message.
        redis.get = AsyncMock(return_value="42")
        redis.set = AsyncMock(return_value=True)
        redis.keys = AsyncMock(return_value=["progress:task:111:parse:1"])
        redis.mget = AsyncMock(return_value=[json.dumps(_task_state())])

        await svc.start_task("parse:1", "Backend Dev", ["🌐 Scraping"])

        bot.send_message.assert_not_called()
        bot.edit_message_text.assert_awaited_once()


# ---------------------------------------------------------------------------
# update_bar
# ---------------------------------------------------------------------------


class TestUpdateBar:
    @pytest.mark.asyncio
    async def test_advances_bar_counter(self):
        state = _task_state(bars=[{"label": "🌐 Scraping", "current": 0, "total": 50}])
        redis = _make_redis(
            pin="42",
            task=json.dumps(state),
            task_keys=["progress:task:111:parse:1"],
            task_values=[json.dumps(state)],
        )
        svc, bot, _ = _make_service(chat_id=111, redis=redis)

        await svc.update_bar("parse:1", 0, 10, 50)

        set_calls = redis.set.call_args_list
        task_set_call = next(c for c in set_calls if "progress:task" in str(c.args[0]))
        saved = json.loads(task_set_call.args[1])
        assert saved["bars"][0]["current"] == 10

    @pytest.mark.asyncio
    async def test_monotonic_guard_does_not_lower_counter(self):
        state = _task_state(bars=[{"label": "🌐 Scraping", "current": 30, "total": 50}])
        redis = _make_redis(pin=None, task=json.dumps(state))
        svc, bot, _ = _make_service(chat_id=111, redis=redis)

        await svc.update_bar("parse:1", 0, 5, 50)

        set_calls = redis.set.call_args_list
        task_set_call = next(c for c in set_calls if "progress:task" in str(c.args[0]))
        saved = json.loads(task_set_call.args[1])
        assert saved["bars"][0]["current"] == 30, "Counter must not go backwards"

    @pytest.mark.asyncio
    async def test_returns_early_when_task_key_absent(self):
        redis = _make_redis(pin=None, task=None)
        svc, bot, _ = _make_service(chat_id=111, redis=redis)

        await svc.update_bar("parse:missing", 0, 5, 50)

        bot.edit_message_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_throttle_skips_edit_on_second_call(self):
        state = _task_state(bars=[{"label": "🌐 Scraping", "current": 0, "total": 50}])

        throttle_count = 0

        async def mock_set(*args, **kwargs):
            nonlocal throttle_count
            if kwargs.get("nx") and "throttle" in args[0]:
                throttle_count += 1
                return throttle_count == 1  # first acquires, second fails
            return True

        redis = _make_redis(
            pin="42",
            task=json.dumps(state),
            task_keys=["progress:task:111:parse:1"],
            task_values=[json.dumps(state)],
        )
        redis.set = mock_set
        svc, bot, _ = _make_service(chat_id=111, redis=redis)

        await svc.update_bar("parse:1", 0, 5, 50)  # throttle acquired → edits
        await svc.update_bar("parse:1", 0, 10, 50)  # throttle held → skips edit

        assert bot.edit_message_text.await_count == 1


# ---------------------------------------------------------------------------
# finish_task
# ---------------------------------------------------------------------------


class TestFinishTask:
    @pytest.mark.asyncio
    async def test_marks_task_completed_and_sets_bars_to_100(self):
        initial = _task_state(bars=[{"label": "🧠 Keywords", "current": 40, "total": 50}])
        completed = _task_state(
            status="completed",
            bars=[{"label": "🧠 Keywords", "current": 50, "total": 50}],
        )
        redis = _make_redis(
            pin="42",
            task=json.dumps(initial),
            task_keys=["progress:task:111:parse:1"],
            task_values=[json.dumps(completed)],
        )
        svc, bot, _ = _make_service(chat_id=111, redis=redis)

        await svc.finish_task("parse:1")

        set_calls = redis.set.call_args_list
        task_set_call = next(c for c in set_calls if "progress:task" in str(c.args[0]))
        saved = json.loads(task_set_call.args[1])
        assert saved["status"] == "completed"
        assert saved["bars"][0]["current"] == 50

    @pytest.mark.asyncio
    async def test_sends_completion_summary_when_all_done(self):
        completed_state = _task_state(
            title="Backend Dev",
            status="completed",
            bars=[{"label": "🧠 Keywords", "current": 50, "total": 50}],
        )
        redis = _make_redis(
            pin="42",
            task=json.dumps(_task_state(title="Backend Dev")),
            task_keys=["progress:task:111:parse:1"],
            task_values=[json.dumps(completed_state)],
        )
        svc, bot, _ = _make_service(chat_id=111, redis=redis)

        await svc.finish_task("parse:1")

        # Last send_message call is the completion summary.
        assert bot.send_message.await_count >= 1
        last_send = bot.send_message.call_args_list[-1]
        sent_text = last_send.kwargs.get("text") or last_send.args[1]
        assert "Backend Dev" in sent_text

    @pytest.mark.asyncio
    async def test_deletes_pinned_message_when_all_done(self):
        completed_state = _task_state(status="completed")
        redis = _make_redis(
            pin="42",
            task=json.dumps(_task_state()),
            task_keys=["progress:task:111:parse:1"],
            task_values=[json.dumps(completed_state)],
        )
        svc, bot, _ = _make_service(chat_id=111, redis=redis)

        await svc.finish_task("parse:1")

        bot.delete_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unpins_message_in_dm_when_all_done(self):
        completed_state = _task_state(status="completed")
        redis = _make_redis(
            pin="42",
            task=json.dumps(_task_state()),
            task_keys=["progress:task:111:parse:1"],
            task_values=[json.dumps(completed_state)],
        )
        svc, bot, _ = _make_service(chat_id=111, redis=redis)

        await svc.finish_task("parse:1")

        bot.unpin_chat_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_does_not_send_summary_when_tasks_still_running(self):
        running_state = _task_state(status="running")
        # pin="42" so _refresh_message edits (no send_message for pin creation).
        redis = _make_redis(
            pin="42",
            task=json.dumps(_task_state()),
            task_keys=["progress:task:111:parse:1"],
            task_values=[json.dumps(running_state)],
        )
        svc, bot, _ = _make_service(chat_id=111, redis=redis)

        await svc.finish_task("parse:1")

        # send_message must NOT be called — completion summary is suppressed.
        bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_missing_task_key_gracefully(self):
        redis = _make_redis(pin=None, task=None)
        svc, bot, _ = _make_service(chat_id=111, redis=redis)

        # Must not raise even when task key is absent.
        await svc.finish_task("parse:missing")


# ---------------------------------------------------------------------------
# _render_progress_text
# ---------------------------------------------------------------------------


class TestRenderProgressText:
    def test_header_uses_progress_title_key(self):
        svc, _, _ = _make_service(locale="en")
        tasks = {"parse:1": _task_state(title="Backend Dev")}
        text = svc._render_progress_text(tasks)
        assert "Processing tasks" in text

    def test_includes_task_title(self):
        svc, _, _ = _make_service()
        tasks = {"parse:1": _task_state(title="Python Dev")}
        text = svc._render_progress_text(tasks)
        assert "Python Dev" in text

    def test_includes_bar_labels(self):
        svc, _, _ = _make_service()
        tasks = {
            "parse:1": _task_state(
                bars=[
                    {"label": "🌐 Scraping", "current": 5, "total": 10},
                    {"label": "🧠 Keywords", "current": 3, "total": 10},
                ]
            )
        }
        text = svc._render_progress_text(tasks)
        assert "🌐 Scraping" in text
        assert "🧠 Keywords" in text

    def test_completed_task_shows_checkmark(self):
        svc, _, _ = _make_service()
        tasks = {
            "parse:1": _task_state(
                title="Backend Dev",
                status="completed",
                bars=[{"label": "🌐 Scraping", "current": 10, "total": 10}],
            )
        }
        text = svc._render_progress_text(tasks)
        assert "✅" in text

    def test_multiple_tasks_all_appear(self):
        svc, _, _ = _make_service()
        tasks = {
            "parse:1": _task_state(title="Backend Dev"),
            "parse:2": _task_state(title="Python Dev"),
        }
        text = svc._render_progress_text(tasks)
        assert "Backend Dev" in text
        assert "Python Dev" in text

    def test_bars_with_zero_total_are_omitted(self):
        svc, _, _ = _make_service()
        tasks = {"parse:1": _task_state(bars=[{"label": "🌐 Scraping", "current": 0, "total": 0}])}
        text = svc._render_progress_text(tasks)
        # Label should not appear because total=0.
        assert "🌐 Scraping" not in text


# ---------------------------------------------------------------------------
# _render_summary
# ---------------------------------------------------------------------------


class TestRenderSummary:
    def test_contains_completed_title(self):
        svc, _, _ = _make_service(locale="en")
        tasks = {"parse:1": _task_state(title="Backend Dev")}
        text = svc._render_summary(tasks)
        assert "All tasks completed" in text

    def test_lists_every_task_title(self):
        svc, _, _ = _make_service()
        tasks = {
            "parse:1": _task_state(title="Backend Dev"),
            "autoparse:2": _task_state(title="Python Dev"),
        }
        text = svc._render_summary(tasks)
        assert "Backend Dev" in text
        assert "Python Dev" in text

    def test_uses_bullet_prefix(self):
        svc, _, _ = _make_service()
        tasks = {"parse:1": _task_state(title="Backend Dev")}
        text = svc._render_summary(tasks)
        assert "•" in text


# ---------------------------------------------------------------------------
# DM detection
# ---------------------------------------------------------------------------


class TestIsDm:
    def test_positive_chat_id_is_dm(self):
        svc, _, _ = _make_service(chat_id=12345)
        assert svc._is_dm is True

    def test_negative_chat_id_is_not_dm(self):
        svc, _, _ = _make_service(chat_id=-100123456)
        assert svc._is_dm is False

    def test_zero_chat_id_is_not_dm(self):
        svc, _, _ = _make_service(chat_id=0)
        assert svc._is_dm is False


# ---------------------------------------------------------------------------
# Duplicate message creation guard (msglock)
# ---------------------------------------------------------------------------


class TestMsglock:
    @pytest.mark.asyncio
    async def test_second_worker_waits_for_existing_pin_after_lock_miss(self):
        """When msglock is held by another worker, we wait and return the pin ID set by it."""
        svc, bot, redis = _make_service(chat_id=111)

        call_count = 0

        async def mock_get(key):
            nonlocal call_count
            if "pin" in key:
                call_count += 1
                # First call: no pin yet.  Second call (after sleep): pin exists.
                return None if call_count == 1 else "99"
            return None

        async def mock_set(*args, **kwargs):
            # Return False when msglock is held; True for all other set calls.
            return not (kwargs.get("nx") and "msglock" in args[0])

        redis.get = mock_get
        redis.set = mock_set

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await svc._get_or_create_pin_message("some text")

        assert result == 99
        bot.send_message.assert_not_called()
