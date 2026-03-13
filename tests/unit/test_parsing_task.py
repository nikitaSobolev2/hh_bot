"""Tests for the manual parsing task: blacklist logic and progress service integration."""

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
            from src.schemas.vacancy import PipelineResult

            captured.append(set(blacklisted_ids or set()))
            return PipelineResult(vacancies=[], keywords=[], skills=[])

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
            patch("src.worker.tasks.parsing._start_progress", new=AsyncMock(return_value=None)),
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


def _make_progress_service(chat_id: int = 111, locale: str = "ru"):
    """Return a ProgressService with a fully mocked bot and Redis client."""
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
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.delete = AsyncMock()
    redis_mock.keys = AsyncMock(return_value=[])
    redis_mock.mget = AsyncMock(return_value=[])

    svc = ProgressService(bot, chat_id, redis_mock, locale)
    return svc, bot, redis_mock


# ---------------------------------------------------------------------------
# _start_progress factory
# ---------------------------------------------------------------------------


class TestStartProgressFactory:
    """_start_progress returns None when no bot/chat_id, otherwise a ProgressService."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_bot(self):
        from src.worker.tasks.parsing import _start_progress

        result = await _start_progress(None, 0, MagicMock(), "ru")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_chat_id_zero(self):
        from src.worker.tasks.parsing import _start_progress

        result = await _start_progress(MagicMock(), 0, MagicMock(), "ru")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_progress_service_when_valid(self):
        from unittest.mock import patch

        from src.services.progress_service import ProgressService
        from src.worker.tasks.parsing import _start_progress

        company = MagicMock()
        company.id = 7
        company.vacancy_title = "Backend Dev"

        task_json = '{"title":"Backend Dev","status":"running","bars":[]}'

        async def _key_router(key):
            if "progress:pin:" in key:
                return None
            if "progress:task:" in key:
                return task_json
            return None

        mock_redis = MagicMock()
        mock_redis.get = _key_router
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.delete = AsyncMock()
        mock_redis.keys = AsyncMock(return_value=["progress:task:100:parse:7"])
        mock_redis.mget = AsyncMock(return_value=[task_json])
        bot = MagicMock()
        msg = MagicMock()
        msg.message_id = 1
        bot.send_message = AsyncMock(return_value=msg)
        bot.edit_message_text = AsyncMock()
        bot.pin_chat_message = AsyncMock()

        with patch(
            "src.services.progress_service.create_progress_redis",
            return_value=mock_redis,
        ):
            result = await _start_progress(bot, 100, company, "ru")

        assert isinstance(result, ProgressService)
