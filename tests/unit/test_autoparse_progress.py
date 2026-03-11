"""Tests for _AutoparseProgressTracker and on_vacancy_scraped callback."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tracker(
    chat_id: int = 100,
    vacancy_title: str = "Fullstack Dev",
    target_count: int = 50,
    keyword_filter: str = "backend|node",
    locale: str = "ru",
):
    """Return a tracker instance with a mocked bot."""
    from src.worker.tasks.autoparse import _AutoparseProgressTracker

    bot = MagicMock()
    bot.send_message_draft = AsyncMock()

    tracker = _AutoparseProgressTracker(
        bot,
        chat_id,
        vacancy_title=vacancy_title,
        target_count=target_count,
        keyword_filter=keyword_filter,
        locale=locale,
    )
    # Bypass throttle so first call always sends.
    tracker._last_send = 0.0
    return tracker, bot


# ---------------------------------------------------------------------------
# Counter tests
# ---------------------------------------------------------------------------


class TestUpdateScraped:
    """update_scraped updates counters and sends a draft."""

    @pytest.mark.asyncio
    async def test_updates_scraped_counter(self):
        tracker, _ = _make_tracker()
        await tracker.update_scraped(5, 50)
        assert tracker._scraped == 5
        assert tracker._scraped_total == 50

    @pytest.mark.asyncio
    async def test_calls_send_message_draft(self):
        tracker, bot = _make_tracker()
        await tracker.update_scraped(1, 50)
        bot.send_message_draft.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_monotonic_guard_does_not_decrease_counter(self):
        tracker, _ = _make_tracker()
        tracker._scraped = 10
        await tracker.update_scraped(5, 50)
        assert tracker._scraped == 10, "Lower current must not overwrite a higher counter"

    @pytest.mark.asyncio
    async def test_advances_when_higher(self):
        tracker, _ = _make_tracker()
        tracker._scraped = 3
        await tracker.update_scraped(7, 50)
        assert tracker._scraped == 7


class TestUpdateAnalyzed:
    """update_analyzed updates counters and sends a draft."""

    @pytest.mark.asyncio
    async def test_updates_analyzed_counter(self):
        tracker, _ = _make_tracker()
        await tracker.update_analyzed(3, 20)
        assert tracker._analyzed == 3
        assert tracker._analyzed_total == 20

    @pytest.mark.asyncio
    async def test_calls_send_message_draft(self):
        tracker, bot = _make_tracker()
        await tracker.update_analyzed(2, 20)
        bot.send_message_draft.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_monotonic_guard_does_not_decrease_counter(self):
        tracker, _ = _make_tracker()
        tracker._analyzed = 15
        await tracker.update_analyzed(8, 20)
        assert tracker._analyzed == 15

    @pytest.mark.asyncio
    async def test_advances_when_higher(self):
        tracker, _ = _make_tracker()
        tracker._analyzed = 5
        await tracker.update_analyzed(12, 20)
        assert tracker._analyzed == 12


# ---------------------------------------------------------------------------
# finish() bypasses throttle
# ---------------------------------------------------------------------------


class TestFinish:
    """finish() must send a draft even when the throttle window is active."""

    @pytest.mark.asyncio
    async def test_sends_draft_when_throttle_active(self):
        tracker, bot = _make_tracker()
        # Simulate a very recent send so the throttle would normally block.
        tracker._last_send = time.monotonic()
        await tracker.finish()
        bot.send_message_draft.assert_awaited_once()


# ---------------------------------------------------------------------------
# Message text content
# ---------------------------------------------------------------------------


class TestBuildText:
    """_build_text produces the expected content."""

    def test_ai_bar_absent_when_analyzed_total_is_zero(self):
        tracker, _ = _make_tracker()
        text = tracker._build_text(10, 50, 0, 0)
        assert "AI-совместимость" not in text
        assert "AI Analysis" not in text

    def test_ai_bar_present_when_analyzed_total_positive(self):
        tracker, _ = _make_tracker()
        text = tracker._build_text(10, 50, 5, 20)
        assert "AI-совместимость" in text

    def test_scraping_bar_always_present(self):
        tracker, _ = _make_tracker()
        text = tracker._build_text(10, 50, 0, 0)
        assert "Парсинг" in text

    def test_keyword_filter_included_when_set(self):
        tracker, _ = _make_tracker(keyword_filter="backend|node")
        text = tracker._build_text(0, 50, 0, 0)
        assert "backend|node" in text

    def test_keyword_filter_omitted_when_empty(self):
        tracker, _ = _make_tracker(keyword_filter="")
        text = tracker._build_text(0, 50, 0, 0)
        assert "🔎" not in text

    def test_vacancy_title_included(self):
        tracker, _ = _make_tracker(vacancy_title="Python Dev")
        text = tracker._build_text(0, 50, 0, 0)
        assert "Python Dev" in text

    def test_english_locale_labels(self):
        tracker, _ = _make_tracker(locale="en")
        text = tracker._build_text(10, 50, 5, 20)
        assert "Processing vacancies" in text
        assert "AI Analysis" in text


# ---------------------------------------------------------------------------
# draft_id is deterministic
# ---------------------------------------------------------------------------


class TestDraftId:
    def test_same_chat_id_same_draft_id(self):
        from src.worker.tasks.autoparse import _AutoparseProgressTracker

        t1 = _AutoparseProgressTracker(
            MagicMock(), 999, vacancy_title="X", target_count=10, keyword_filter=""
        )
        t2 = _AutoparseProgressTracker(
            MagicMock(), 999, vacancy_title="Y", target_count=50, keyword_filter="k"
        )
        assert t1._draft_id == t2._draft_id

    def test_draft_id_in_valid_range(self):
        from src.worker.tasks.autoparse import _AutoparseProgressTracker

        tracker = _AutoparseProgressTracker(
            MagicMock(), 123456789, vacancy_title="X", target_count=5, keyword_filter=""
        )
        assert 1 <= tracker._draft_id <= 2**31 - 1


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
        scraper._vacancy_delay = (0, 0)
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
        scraper._vacancy_delay = (0, 0)
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
        scraper._vacancy_delay = (0, 0)
        scraper.parse_vacancy_page = AsyncMock(
            return_value={"title": "Dev", "description": "...", "skills": []}
        )

        from src.services.parser.hh_parser_service import HHParserService

        service = HHParserService(scraper=scraper)
        results = await service.parse_vacancies("https://hh.ru/search", "python", 10)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Flood / bad-request handling
# ---------------------------------------------------------------------------


class TestDraftSendErrorHandling:
    """TelegramRetryAfter and TelegramBadRequest are caught and do not raise."""

    @pytest.mark.asyncio
    async def test_retry_after_is_caught(self):
        from aiogram.exceptions import TelegramRetryAfter

        tracker, bot = _make_tracker()
        exc = TelegramRetryAfter(retry_after=1, message="", method=MagicMock())
        bot.send_message_draft = AsyncMock(side_effect=exc)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await tracker.update_scraped(1, 10)  # must not raise

    @pytest.mark.asyncio
    async def test_bad_request_is_caught(self):
        from aiogram.exceptions import TelegramBadRequest

        tracker, bot = _make_tracker()
        exc = TelegramBadRequest(message="", method=MagicMock())
        bot.send_message_draft = AsyncMock(side_effect=exc)

        await tracker.update_scraped(1, 10)  # must not raise
