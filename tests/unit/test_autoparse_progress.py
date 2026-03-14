"""Tests for autoparse progress integration and on_vacancy_scraped callback."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _key_router(*, pin=None, task=None):
    """Return an async callable routing redis.get calls by key prefix."""

    async def _get(key: str):
        if "progress:pin:" in key:
            return pin
        if "progress:task:" in key:
            return task
        return None

    return _get


def _make_progress_service(
    chat_id: int = 100,
    locale: str = "ru",
    *,
    pin=None,
    task=None,
    task_keys=None,
    task_values=None,
):
    """Return a ProgressService with a key-aware mocked Redis client."""
    from src.services.progress_service import ProgressService

    bot = MagicMock()
    msg = MagicMock()
    msg.message_id = 42
    bot.send_message = AsyncMock(return_value=msg)
    bot.edit_message_text = AsyncMock()
    bot.pin_chat_message = AsyncMock()
    bot.unpin_chat_message = AsyncMock()
    bot.delete_message = AsyncMock()

    redis_mock = MagicMock()
    redis_mock.get = _key_router(pin=pin, task=task)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.delete = AsyncMock()
    redis_mock.keys = AsyncMock(return_value=task_keys or [])
    redis_mock.mget = AsyncMock(return_value=task_values or [])

    svc = ProgressService(bot, chat_id, redis_mock, locale)
    return svc, bot, redis_mock


# ---------------------------------------------------------------------------
# update_bar — scraping bar (index 0) via ProgressService
# ---------------------------------------------------------------------------


class TestUpdateScrapingBar:
    """update_bar with bar_index=0 advances the scraping counter monotonically."""

    @pytest.mark.asyncio
    async def test_advances_scraping_counter(self):
        state = {
            "title": "Dev",
            "status": "running",
            "bars": [
                {"label": "🌐 Scraping", "current": 0, "total": 50},
                {"label": "🧠 AI", "current": 0, "total": 0},
            ],
        }
        svc, _bot, redis = _make_progress_service(
            pin="42",
            task=json.dumps(state),
            task_keys=["progress:task:100:autoparse:1"],
            task_values=[json.dumps(state)],
        )

        await svc.update_bar("autoparse:1", 0, 5, 50)

        set_calls = redis.set.call_args_list
        task_call = next(c for c in set_calls if "progress:task" in str(c.args[0]))
        saved = json.loads(task_call.args[1])
        assert saved["bars"][0]["current"] == 5

    @pytest.mark.asyncio
    async def test_monotonic_guard_scraping(self):
        state = {
            "title": "Dev",
            "status": "running",
            "bars": [
                {"label": "🌐 Scraping", "current": 10, "total": 50},
            ],
        }
        svc, _bot, redis = _make_progress_service(pin=None, task=json.dumps(state))

        await svc.update_bar("autoparse:1", 0, 5, 50)

        set_calls = redis.set.call_args_list
        task_call = next(c for c in set_calls if "progress:task" in str(c.args[0]))
        saved = json.loads(task_call.args[1])
        assert saved["bars"][0]["current"] == 10, "Counter must not go backwards"


# ---------------------------------------------------------------------------
# update_bar — AI analysis bar (index 1) via ProgressService
# ---------------------------------------------------------------------------


class TestUpdateAiBar:
    """update_bar with bar_index=1 advances the AI analysis counter monotonically."""

    @pytest.mark.asyncio
    async def test_advances_ai_counter(self):
        state = {
            "title": "Dev",
            "status": "running",
            "bars": [
                {"label": "🌐 Scraping", "current": 50, "total": 50},
                {"label": "🧠 AI", "current": 0, "total": 20},
            ],
        }
        svc, _bot, redis = _make_progress_service(
            pin="42",
            task=json.dumps(state),
            task_keys=["progress:task:100:autoparse:1"],
            task_values=[json.dumps(state)],
        )

        await svc.update_bar("autoparse:1", 1, 3, 20)

        set_calls = redis.set.call_args_list
        task_call = next(c for c in set_calls if "progress:task" in str(c.args[0]))
        saved = json.loads(task_call.args[1])
        assert saved["bars"][1]["current"] == 3

    @pytest.mark.asyncio
    async def test_monotonic_guard_ai(self):
        state = {
            "title": "Dev",
            "status": "running",
            "bars": [
                {"label": "🌐 Scraping", "current": 50, "total": 50},
                {"label": "🧠 AI", "current": 15, "total": 20},
            ],
        }
        svc, _bot, redis = _make_progress_service(pin=None, task=json.dumps(state))

        await svc.update_bar("autoparse:1", 1, 8, 20)

        set_calls = redis.set.call_args_list
        task_call = next(c for c in set_calls if "progress:task" in str(c.args[0]))
        saved = json.loads(task_call.args[1])
        assert saved["bars"][1]["current"] == 15, "Counter must not go backwards"


# ---------------------------------------------------------------------------
# finish_task — final state and completion
# ---------------------------------------------------------------------------


class TestFinishTask:
    """finish_task marks task done and triggers summary when all tasks complete."""

    @pytest.mark.asyncio
    async def test_marks_completed_and_sets_bars_to_100(self):
        initial = {
            "title": "Dev",
            "status": "running",
            "bars": [
                {"label": "🌐 Scraping", "current": 40, "total": 50},
            ],
        }
        completed_state = {
            "title": "Dev",
            "status": "completed",
            "bars": [
                {"label": "🌐 Scraping", "current": 50, "total": 50},
            ],
        }
        svc, _bot, redis = _make_progress_service(
            pin="42",
            task=json.dumps(initial),
            task_keys=["progress:task:100:autoparse:1"],
            task_values=[json.dumps(completed_state)],
        )

        await svc.finish_task("autoparse:1")

        set_calls = redis.set.call_args_list
        task_call = next(c for c in set_calls if "progress:task" in str(c.args[0]))
        saved = json.loads(task_call.args[1])
        assert saved["status"] == "completed"
        assert saved["bars"][0]["current"] == 50


# ---------------------------------------------------------------------------
# on_vacancy_scraped callback in HHParserService.parse_vacancies
# ---------------------------------------------------------------------------


class TestOnVacancyScrapedCallback:
    """parse_vacancies calls on_vacancy_scraped once per new (non-cached) vacancy."""

    @pytest.mark.asyncio
    async def test_callback_called_once_per_new_vacancy(self):
        scraper = MagicMock()
        scraper.collect_vacancy_urls = AsyncMock(
            return_value=[
                {"hh_vacancy_id": "1", "url": "https://hh.ru/vacancy/1"},
                {"hh_vacancy_id": "2", "url": "https://hh.ru/vacancy/2"},
            ]
        )
        scraper.parse_vacancy_page = AsyncMock(
            return_value={"title": "Dev", "description": "...", "skills": []}
        )

        calls: list[tuple[int, int]] = []

        async def on_scraped(current: int, total: int) -> None:
            calls.append((current, total))

        from src.services.parser.hh_parser_service import HHParserService

        service = HHParserService(scraper=scraper)
        await service.parse_vacancies(
            "https://hh.ru/search",
            "python",
            10,
            on_vacancy_scraped=on_scraped,
        )

        assert calls == [(1, 10), (2, 10)], f"Expected one callback per new vacancy; got {calls}"

    @pytest.mark.asyncio
    async def test_callback_not_called_for_cached_vacancies(self):
        scraper = MagicMock()
        scraper.collect_vacancy_urls = AsyncMock(
            return_value=[
                {"hh_vacancy_id": "already_known", "url": "https://hh.ru/vacancy/99"},
            ]
        )
        scraper.parse_vacancy_page = AsyncMock(return_value=None)

        calls: list = []

        async def on_scraped(current: int, total: int) -> None:
            calls.append((current, total))

        from src.services.parser.hh_parser_service import HHParserService

        service = HHParserService(scraper=scraper)
        await service.parse_vacancies(
            "https://hh.ru/search",
            "python",
            10,
            known_hh_ids={"already_known"},
            on_vacancy_scraped=on_scraped,
        )

        assert calls == [], "Callback must not be called for cached vacancies"

    @pytest.mark.asyncio
    async def test_no_callback_when_not_provided(self):
        """parse_vacancies must work fine when on_vacancy_scraped is None."""
        scraper = MagicMock()
        scraper.collect_vacancy_urls = AsyncMock(
            return_value=[{"hh_vacancy_id": "1", "url": "https://hh.ru/vacancy/1"}]
        )
        scraper.parse_vacancy_page = AsyncMock(
            return_value={"title": "Dev", "description": "...", "skills": []}
        )

        from src.services.parser.hh_parser_service import HHParserService

        service = HHParserService(scraper=scraper)
        results = await service.parse_vacancies("https://hh.ru/search", "python", 10)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Telegram error handling — ProgressService catches API errors gracefully
# ---------------------------------------------------------------------------


class TestTelegramErrorHandling:
    """TelegramRetryAfter and TelegramBadRequest are caught and do not raise."""

    @pytest.mark.asyncio
    async def test_retry_after_is_caught_on_edit(self):
        from unittest.mock import patch

        from aiogram.exceptions import TelegramRetryAfter

        state = {
            "title": "Dev",
            "status": "running",
            "bars": [{"label": "🌐 Scraping", "current": 5, "total": 50}],
        }
        svc, bot, redis = _make_progress_service(
            pin="42",
            task=json.dumps(state),
            task_keys=["progress:task:100:autoparse:1"],
            task_values=[json.dumps(state)],
        )

        exc = TelegramRetryAfter(retry_after=1, message="", method=MagicMock())
        bot.edit_message_text = AsyncMock(side_effect=exc)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await svc.update_bar("autoparse:1", 0, 5, 50)  # must not raise

    @pytest.mark.asyncio
    async def test_bad_request_on_edit_is_caught(self):
        from aiogram.exceptions import TelegramBadRequest

        state = {
            "title": "Dev",
            "status": "running",
            "bars": [{"label": "🌐 Scraping", "current": 5, "total": 50}],
        }
        svc, bot, redis = _make_progress_service(
            pin="42",
            task=json.dumps(state),
            task_keys=["progress:task:100:autoparse:1"],
            task_values=[json.dumps(state)],
        )

        exc = TelegramBadRequest(message="", method=MagicMock())
        bot.edit_message_text = AsyncMock(side_effect=exc)

        await svc.update_bar("autoparse:1", 0, 5, 50)  # must not raise
