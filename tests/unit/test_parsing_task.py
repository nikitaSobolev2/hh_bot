"""Tests for the manual parsing task: blacklist logic and progress tracker."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestManualParseBlacklist:
    """Ensure AutoparsedVacancy IDs are never merged into the manual parse blacklist.

    We test this at the source-code level: the function must not import
    AutoparsedVacancyRepository or call get_all_known_hh_ids.  This is
    deliberately simple — the integration-level evidence is the fixed
    log output (blacklisted_skipped=0 for a fresh user blacklist).
    """

    def test_autoparse_repository_not_imported_in_parsing_task(self):
        """AutoparsedVacancyRepository must not appear in _run_parsing_company_async."""
        import inspect

        from src.worker.tasks import parsing as parsing_module

        source = inspect.getsource(parsing_module._run_parsing_company_async)
        assert "AutoparsedVacancyRepository" not in source, (
            "_run_parsing_company_async must not use AutoparsedVacancyRepository; "
            "it incorrectly merges autoparse IDs into the user blacklist"
        )

    def test_cached_ids_not_merged_into_blacklist(self):
        """The phrase 'cached_ids' must not appear in _run_parsing_company_async."""
        import inspect

        from src.worker.tasks import parsing as parsing_module

        source = inspect.getsource(parsing_module._run_parsing_company_async)
        assert "cached_ids" not in source, (
            "cached_ids must not be added to blacklisted_ids in the manual parse task"
        )

    @pytest.mark.asyncio
    async def test_run_pipeline_receives_only_user_blacklist(self):
        """ParsingExtractor.run_pipeline must be called with only user-blacklist IDs."""
        from unittest.mock import AsyncMock, MagicMock, patch

        user_blacklist_ids = {"id_aaa", "id_bbb"}
        autoparse_ids = {"id_ccc", "id_ddd"}

        captured: list[set] = []

        async def fake_run_pipeline(
            _self,
            search_url,
            keyword_filter,
            target_count,
            *,
            blacklisted_ids=None,
            on_page_scraped=None,
            on_vacancy_processed=None,
            **_kwargs,
        ):
            captured.append(set(blacklisted_ids or set()))
            return {"vacancies": [], "keywords": {}, "skills": {}}

        company = MagicMock()
        company.vacancy_title = "Backend"
        company.search_url = "https://hh.ru/search/vacancy?text=backend"
        company.keyword_filter = "backend"
        company.target_count = 10
        company.status = "pending"
        company.use_compatibility_check = False
        company.compatibility_threshold = None

        settings_repo = AsyncMock()
        settings_repo.get_value = AsyncMock(return_value=True)

        bl_repo = AsyncMock()
        bl_repo.get_active_ids = AsyncMock(return_value=user_blacklist_ids)

        company_repo = AsyncMock()
        company_repo.get_by_id = AsyncMock(return_value=company)
        company_repo.update = AsyncMock()

        task_repo = AsyncMock()
        task_repo.get_by_idempotency_key = AsyncMock(return_value=None)

        ap_repo = AsyncMock()
        ap_repo.get_all_known_hh_ids = AsyncMock(return_value=autoparse_ids)

        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        session.commit = AsyncMock()

        session_factory = MagicMock(return_value=session)

        from src.worker.tasks.parsing import _run_parsing_company_async

        with (
            patch(
                "src.worker.tasks.parsing._init_bot_and_locale",
                new=AsyncMock(return_value=(None, "ru")),
            ),
            patch("src.worker.tasks.parsing._make_tracker", return_value=None),
            patch("src.worker.tasks.parsing._save_parsing_results", new=AsyncMock()),
            patch("src.worker.tasks.parsing._notify_user", new=AsyncMock()),
            patch("src.worker.circuit_breaker.CircuitBreaker.is_call_allowed", return_value=True),
            patch("src.worker.circuit_breaker.CircuitBreaker.record_success"),
            patch(
                "src.repositories.app_settings.AppSettingRepository",
                return_value=settings_repo,
            ),
            patch("src.repositories.blacklist.BlacklistRepository", return_value=bl_repo),
            patch(
                "src.repositories.parsing.ParsingCompanyRepository",
                return_value=company_repo,
            ),
            patch("src.repositories.task.CeleryTaskRepository", return_value=task_repo),
            patch(
                "src.repositories.autoparse.AutoparsedVacancyRepository",
                return_value=ap_repo,
            ),
            patch(
                "src.services.parser.extractor.ParsingExtractor.run_pipeline",
                new=fake_run_pipeline,
            ),
        ):
            fake_task = MagicMock()
            fake_task.request.id = "test-id"

            await _run_parsing_company_async(
                session_factory,
                fake_task,
                parsing_company_id=1,
                user_id=42,
                include_blacklisted=False,
                telegram_chat_id=0,
            )

        assert len(captured) == 1, "run_pipeline must be called exactly once"
        passed_blacklist = captured[0]

        assert user_blacklist_ids.issubset(passed_blacklist), "User blacklist IDs must be present"
        assert not autoparse_ids.intersection(passed_blacklist), (
            f"Autoparse IDs {autoparse_ids} must NOT be in the blacklist passed to run_pipeline; "
            f"got {passed_blacklist}"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tracker(chat_id: int = 111, slot_key: str = "42", locale: str = "ru"):
    """Return a _ProgressTracker with a mocked bot and Redis client."""
    from src.worker.tasks.parsing import _ProgressTracker

    bot = MagicMock()
    bot.send_message_draft = AsyncMock()

    tracker = _ProgressTracker(
        bot,
        chat_id,
        slot_key=slot_key,
        vacancy_title="Backend Dev",
        target_count=100,
        keyword_filter="python",
        locale=locale,
    )

    # Inject a mock async Redis client so no real Redis is needed.
    redis_mock = MagicMock()
    redis_mock.set = AsyncMock()
    redis_mock.delete = AsyncMock()
    redis_mock.keys = AsyncMock(return_value=[])
    redis_mock.mget = AsyncMock(return_value=[])
    tracker._redis = redis_mock

    return tracker, bot, redis_mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProgressTrackerMonotonic:
    """update_scraped / update_keywords must never move the counter backwards."""

    @pytest.mark.asyncio
    async def test_update_keywords_ignores_lower_current_value(self):
        """Writing current=99 after current=100 must not lower self._keywords."""
        tracker, _bot, redis_mock = _make_tracker()
        redis_mock.keys = AsyncMock(return_value=["progress:111:42"])
        redis_mock.mget = AsyncMock(
            return_value=[json.dumps({"scraped": 0, "keywords": 100, "total": 100})]
        )

        # Simulate task-100 writing first.
        async with tracker._lock:
            tracker._keywords = 100
            tracker._total = 100

        # Now task-99 arrives — it must not overwrite the higher value.
        await tracker.update_keywords(99, 100)

        assert tracker._keywords == 100, "A lower current value must not overwrite a higher one"

    @pytest.mark.asyncio
    async def test_update_keywords_advances_when_higher(self):
        """Normal forward progress must still advance self._keywords."""
        tracker, _bot, redis_mock = _make_tracker()
        redis_mock.keys = AsyncMock(return_value=["progress:111:42"])
        redis_mock.mget = AsyncMock(
            return_value=[json.dumps({"scraped": 0, "keywords": 5, "total": 100})]
        )

        await tracker.update_keywords(10, 100)

        assert tracker._keywords == 10

    @pytest.mark.asyncio
    async def test_update_scraped_ignores_lower_current_value(self):
        """Writing current=50 after current=80 must not lower self._scraped."""
        tracker, _bot, redis_mock = _make_tracker()
        redis_mock.keys = AsyncMock(return_value=["progress:111:42"])
        redis_mock.mget = AsyncMock(
            return_value=[json.dumps({"scraped": 80, "keywords": 0, "total": 100})]
        )

        async with tracker._lock:
            tracker._scraped = 80
            tracker._total = 100

        await tracker.update_scraped(50, 100)

        assert tracker._scraped == 80

    @pytest.mark.asyncio
    async def test_update_scraped_advances_when_higher(self):
        tracker, _bot, redis_mock = _make_tracker()
        redis_mock.keys = AsyncMock(return_value=["progress:111:42"])
        redis_mock.mget = AsyncMock(
            return_value=[json.dumps({"scraped": 3, "keywords": 0, "total": 100})]
        )

        await tracker.update_scraped(20, 100)

        assert tracker._scraped == 20


class TestProgressTrackerDraftId:
    """draft_id must be deterministic and shared across same chat_id."""

    def test_same_chat_id_produces_same_draft_id(self):
        from src.worker.tasks.parsing import _ProgressTracker

        def make(slot: str) -> _ProgressTracker:
            return _ProgressTracker(
                MagicMock(),
                999,
                slot_key=slot,
                vacancy_title="X",
                target_count=10,
                keyword_filter="",
            )

        t1 = make("1")
        t2 = make("2")
        assert t1._draft_id == t2._draft_id, (
            "Two trackers for the same chat_id must share the same draft_id"
        )

    def test_different_chat_ids_may_differ(self):
        from src.worker.tasks.parsing import _ProgressTracker

        def make(chat_id: int) -> _ProgressTracker:
            return _ProgressTracker(
                MagicMock(),
                chat_id,
                slot_key="1",
                vacancy_title="X",
                target_count=10,
                keyword_filter="",
            )

        # Different chat IDs should not collide (trivial sanity check).
        ids = {make(c)._draft_id for c in range(1, 20)}
        assert len(ids) > 1, "Different chat IDs must generally produce different draft_ids"

    def test_draft_id_is_in_valid_range(self):
        from src.worker.tasks.parsing import _ProgressTracker

        tracker = _ProgressTracker(
            MagicMock(),
            123456789,
            slot_key="7",
            vacancy_title="X",
            target_count=5,
            keyword_filter="",
        )
        assert 1 <= tracker._draft_id <= 2**31 - 1


class TestProgressTrackerCombinedDraft:
    """When Redis holds multiple slots, _build_combined_text renders all of them."""

    def test_build_combined_text_includes_all_slot_titles(self):
        from src.worker.tasks.parsing import _ProgressTracker

        tracker = _ProgressTracker(
            MagicMock(),
            111,
            slot_key="1",
            vacancy_title="Backend Dev",
            target_count=100,
            keyword_filter="",
        )

        slots = [
            {
                "scraped": 50,
                "keywords": 40,
                "total": 100,
                "title": "Backend Dev",
                "target_count": 100,
                "keyword_filter": "",
            },
            {
                "scraped": 10,
                "keywords": 8,
                "total": 50,
                "title": "Python Dev",
                "target_count": 50,
                "keyword_filter": "django",
            },
        ]
        text = tracker._build_combined_text(slots)

        assert "Backend Dev" in text
        assert "Python Dev" in text
        assert "django" in text

    @pytest.mark.asyncio
    async def test_send_draft_uses_combined_text_for_two_slots(self):
        """When Redis returns 2 slots, send_message_draft receives combined text."""
        tracker, bot, redis_mock = _make_tracker(slot_key="1")

        slot1 = json.dumps(
            {
                "scraped": 50,
                "keywords": 40,
                "total": 100,
                "title": "Backend Dev",
                "target_count": 100,
                "keyword_filter": "",
            }
        )
        slot2 = json.dumps(
            {
                "scraped": 10,
                "keywords": 8,
                "total": 50,
                "title": "Python Dev",
                "target_count": 50,
                "keyword_filter": "django",
            }
        )
        redis_mock.keys = AsyncMock(return_value=["progress:111:1", "progress:111:2"])
        redis_mock.mget = AsyncMock(return_value=[slot1, slot2])

        # Force throttle bypass by setting _last_send to zero.
        tracker._last_send = 0.0
        tracker._total = 100

        await tracker._send_draft(is_last=False)

        bot.send_message_draft.assert_awaited_once()
        sent_text = bot.send_message_draft.call_args.kwargs["text"]
        assert "Backend Dev" in sent_text
        assert "Python Dev" in sent_text


class TestProgressTrackerSlotCleanup:
    """Redis slot is deleted exactly once when is_last=True."""

    @pytest.mark.asyncio
    async def test_slot_deleted_on_is_last(self):
        tracker, _bot, redis_mock = _make_tracker()
        slot_data = json.dumps(
            {
                "scraped": 100,
                "keywords": 100,
                "total": 100,
                "title": "Backend Dev",
                "target_count": 100,
                "keyword_filter": "",
            }
        )
        redis_mock.keys = AsyncMock(return_value=["progress:111:42"])
        redis_mock.mget = AsyncMock(return_value=[slot_data])

        tracker._last_send = 0.0
        tracker._keywords = 100
        tracker._scraped = 100
        tracker._total = 100

        await tracker._send_draft(is_last=True)

        redis_mock.delete.assert_awaited_once_with("progress:111:42")

    @pytest.mark.asyncio
    async def test_slot_not_deleted_on_intermediate_update(self):
        tracker, _bot, redis_mock = _make_tracker()
        slot_data = json.dumps(
            {
                "scraped": 50,
                "keywords": 40,
                "total": 100,
                "title": "Backend Dev",
                "target_count": 100,
                "keyword_filter": "",
            }
        )
        redis_mock.keys = AsyncMock(return_value=["progress:111:42"])
        redis_mock.mget = AsyncMock(return_value=[slot_data])

        tracker._last_send = 0.0
        tracker._scraped = 50
        tracker._total = 100

        await tracker._send_draft(is_last=False)

        redis_mock.delete.assert_not_awaited()
