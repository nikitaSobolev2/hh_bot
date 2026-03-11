"""Integration tests for Celery task progress service wiring.

These tests verify that _run_autoparse_company_async correctly integrates with
ProgressService: starting the task on entry, updating bars during scraping and
AI analysis, finishing on success, and finishing (for cleanup) even when an
exception is raised.

All imports inside _run_autoparse_company_async are lazy (local), so patches
must target source modules (e.g. src.services.progress_service.ProgressService)
rather than the calling module.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_company(company_id: int = 5, vacancy_title: str = "Backend Dev"):
    c = MagicMock()
    c.id = company_id
    c.vacancy_title = vacancy_title
    c.search_url = "https://hh.ru/search/vacancy?text=backend"
    c.keyword_filter = ""
    c.is_enabled = True
    c.is_deleted = False
    c.user_id = 42
    c.total_runs = 0
    c.total_vacancies_found = 0
    return c


def _make_user(telegram_id: int = 100):
    u = MagicMock()
    u.id = 42
    u.telegram_id = telegram_id
    u.language_code = "ru"
    u.autoparse_settings = {}
    return u


def _make_sync_redis():
    r = MagicMock()
    r.eval = MagicMock(return_value=1)
    r.delete = MagicMock()
    return r


def _make_checkpoint_mock():
    mock = MagicMock()
    mock.load = AsyncMock(return_value=None)
    mock.save = AsyncMock()
    mock.clear = AsyncMock()
    return mock


def _make_mock_bot():
    """Return a mocked aiogram Bot whose session.close() is awaitable."""
    bot = MagicMock()
    bot.session = MagicMock()
    bot.session.close = AsyncMock()
    return bot


def _make_session():
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session


def _repo_patches(company, user):
    """Return a context-manager stack that patches all repository constructors."""
    company_repo = AsyncMock()
    company_repo.get_by_id = AsyncMock(return_value=company)
    company_repo.update = AsyncMock()

    vacancy_repo = AsyncMock()
    vacancy_repo.get_known_hh_ids_for_company = AsyncMock(return_value=set())
    vacancy_repo.get_all_known_hh_ids = AsyncMock(return_value=set())

    parsed_repo = AsyncMock()
    parsed_repo.get_all_hh_ids = AsyncMock(return_value=set())

    settings_repo = AsyncMock()
    settings_repo.get_value = AsyncMock(return_value=10)

    user_repo = AsyncMock()
    user_repo.get_by_id = AsyncMock(return_value=user)

    we_repo = AsyncMock()
    we_repo.get_active_by_user = AsyncMock(return_value=[])

    patches = [
        patch(
            "src.repositories.autoparse.AutoparseCompanyRepository",
            return_value=company_repo,
        ),
        patch(
            "src.repositories.autoparse.AutoparsedVacancyRepository",
            return_value=vacancy_repo,
        ),
        patch(
            "src.repositories.parsing.ParsedVacancyRepository",
            return_value=parsed_repo,
        ),
        patch(
            "src.repositories.app_settings.AppSettingRepository",
            return_value=settings_repo,
        ),
        patch(
            "src.repositories.user.UserRepository",
            return_value=user_repo,
        ),
        patch(
            "src.repositories.work_experience.WorkExperienceRepository",
            return_value=we_repo,
        ),
    ]
    return patches


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAutoparseTaskProgressIntegration:
    """_run_autoparse_company_async wires ProgressService correctly."""

    @pytest.mark.asyncio
    async def test_progress_start_task_called_when_notify_user_id_given(self):
        """start_task is called once with the right task_key and vacancy title."""
        company = _make_company(company_id=5, vacancy_title="Python Dev")
        user = _make_user(telegram_id=111)
        session = _make_session()
        session_factory = MagicMock(return_value=session)
        fake_task = MagicMock()
        fake_task.request.id = "test-id-1"

        progress_mock = AsyncMock()

        base_patches = [
            patch("src.worker.tasks.autoparse._redis_client", return_value=_make_sync_redis()),
            patch("src.worker.circuit_breaker.CircuitBreaker.is_call_allowed", return_value=True),
            patch("src.worker.circuit_breaker.CircuitBreaker.record_success"),
            patch(
                "src.services.parser.hh_parser_service.HHParserService.parse_vacancies",
                new=AsyncMock(return_value=[]),
            ),
            patch("src.services.progress_service.ProgressService", return_value=progress_mock),
            patch("src.services.progress_service.create_progress_redis", return_value=MagicMock()),
            patch(
                "src.services.task_checkpoint.TaskCheckpointService",
                return_value=_make_checkpoint_mock(),
            ),
            patch("src.worker.tasks.autoparse.deliver_autoparse_results"),
            patch(
                "src.worker.tasks.autoparse._send_run_completed_notification",
                new=AsyncMock(),
            ),
            patch("aiogram.Bot", return_value=_make_mock_bot()),
        ]

        from contextlib import ExitStack

        with ExitStack() as stack:
            for p in base_patches + _repo_patches(company, user):
                stack.enter_context(p)

            from src.worker.tasks.autoparse import _run_autoparse_company_async

            await _run_autoparse_company_async(
                session_factory,
                fake_task,
                company_id=5,
                notify_user_id=42,
            )

        progress_mock.start_task.assert_awaited_once()
        kwargs = progress_mock.start_task.call_args.kwargs
        assert kwargs["task_key"] == "autoparse:5"
        assert kwargs["title"] == "Python Dev"

    @pytest.mark.asyncio
    async def test_progress_finish_task_called_on_success(self):
        """finish_task is always called (via finally) after successful execution."""
        company = _make_company(company_id=7)
        user = _make_user(telegram_id=222)
        session = _make_session()
        session_factory = MagicMock(return_value=session)
        fake_task = MagicMock()
        fake_task.request.id = "test-id-2"

        progress_mock = AsyncMock()

        base_patches = [
            patch("src.worker.tasks.autoparse._redis_client", return_value=_make_sync_redis()),
            patch("src.worker.circuit_breaker.CircuitBreaker.is_call_allowed", return_value=True),
            patch("src.worker.circuit_breaker.CircuitBreaker.record_success"),
            patch(
                "src.services.parser.hh_parser_service.HHParserService.parse_vacancies",
                new=AsyncMock(return_value=[]),
            ),
            patch("src.services.progress_service.ProgressService", return_value=progress_mock),
            patch("src.services.progress_service.create_progress_redis", return_value=MagicMock()),
            patch(
                "src.services.task_checkpoint.TaskCheckpointService",
                return_value=_make_checkpoint_mock(),
            ),
            patch("src.worker.tasks.autoparse.deliver_autoparse_results"),
            patch(
                "src.worker.tasks.autoparse._send_run_completed_notification",
                new=AsyncMock(),
            ),
            patch("aiogram.Bot", return_value=_make_mock_bot()),
        ]

        from contextlib import ExitStack

        with ExitStack() as stack:
            for p in base_patches + _repo_patches(company, user):
                stack.enter_context(p)

            from src.worker.tasks.autoparse import _run_autoparse_company_async

            result = await _run_autoparse_company_async(
                session_factory,
                fake_task,
                company_id=7,
                notify_user_id=42,
            )

        assert result["status"] == "completed"
        progress_mock.finish_task.assert_awaited_once_with("autoparse:7")

    @pytest.mark.asyncio
    async def test_progress_finish_task_called_on_exception(self):
        """finish_task is called via finally even when an exception is raised."""
        company = _make_company(company_id=9)
        user = _make_user(telegram_id=333)
        session = _make_session()
        session_factory = MagicMock(return_value=session)
        fake_task = MagicMock()
        fake_task.request.id = "test-id-3"

        progress_mock = AsyncMock()

        base_patches = [
            patch("src.worker.tasks.autoparse._redis_client", return_value=_make_sync_redis()),
            patch("src.worker.circuit_breaker.CircuitBreaker.is_call_allowed", return_value=True),
            patch("src.worker.circuit_breaker.CircuitBreaker.record_failure"),
            patch(
                "src.services.parser.hh_parser_service.HHParserService.parse_vacancies",
                new=AsyncMock(side_effect=RuntimeError("scraping failed")),
            ),
            patch("src.services.progress_service.ProgressService", return_value=progress_mock),
            patch("src.services.progress_service.create_progress_redis", return_value=MagicMock()),
            patch(
                "src.services.task_checkpoint.TaskCheckpointService",
                return_value=_make_checkpoint_mock(),
            ),
            patch("aiogram.Bot", return_value=_make_mock_bot()),
        ]

        from contextlib import ExitStack

        with ExitStack() as stack:
            for p in base_patches + _repo_patches(company, user):
                stack.enter_context(p)

            from src.worker.tasks.autoparse import _run_autoparse_company_async

            with pytest.raises(RuntimeError, match="scraping failed"):
                await _run_autoparse_company_async(
                    session_factory,
                    fake_task,
                    company_id=9,
                    notify_user_id=42,
                )

        progress_mock.finish_task.assert_awaited_once_with("autoparse:9")

    @pytest.mark.asyncio
    async def test_finish_task_exception_does_not_suppress_original_error(self):
        """If finish_task itself raises, the original task exception still propagates."""
        company = _make_company(company_id=11)
        user = _make_user(telegram_id=444)
        session = _make_session()
        session_factory = MagicMock(return_value=session)
        fake_task = MagicMock()
        fake_task.request.id = "test-id-4"

        progress_mock = AsyncMock()
        progress_mock.finish_task = AsyncMock(side_effect=ValueError("redis down"))

        base_patches = [
            patch("src.worker.tasks.autoparse._redis_client", return_value=_make_sync_redis()),
            patch("src.worker.circuit_breaker.CircuitBreaker.is_call_allowed", return_value=True),
            patch("src.worker.circuit_breaker.CircuitBreaker.record_failure"),
            patch(
                "src.services.parser.hh_parser_service.HHParserService.parse_vacancies",
                new=AsyncMock(side_effect=RuntimeError("parsing failed")),
            ),
            patch("src.services.progress_service.ProgressService", return_value=progress_mock),
            patch("src.services.progress_service.create_progress_redis", return_value=MagicMock()),
            patch(
                "src.services.task_checkpoint.TaskCheckpointService",
                return_value=_make_checkpoint_mock(),
            ),
            patch("aiogram.Bot", return_value=_make_mock_bot()),
        ]

        from contextlib import ExitStack

        with ExitStack() as stack:
            for p in base_patches + _repo_patches(company, user):
                stack.enter_context(p)

            from src.worker.tasks.autoparse import _run_autoparse_company_async

            # The original RuntimeError must propagate; ValueError from finish_task is suppressed.
            with pytest.raises(RuntimeError, match="parsing failed"):
                await _run_autoparse_company_async(
                    session_factory,
                    fake_task,
                    company_id=11,
                    notify_user_id=42,
                )

    @pytest.mark.asyncio
    async def test_no_progress_when_notify_user_id_is_none(self):
        """ProgressService is never constructed when notify_user_id is None."""
        company = _make_company(company_id=13)
        user = _make_user(telegram_id=555)
        session = _make_session()
        session_factory = MagicMock(return_value=session)
        fake_task = MagicMock()
        fake_task.request.id = "test-id-5"

        progress_cls_mock = MagicMock()

        base_patches = [
            patch("src.worker.tasks.autoparse._redis_client", return_value=_make_sync_redis()),
            patch("src.worker.circuit_breaker.CircuitBreaker.is_call_allowed", return_value=True),
            patch("src.worker.circuit_breaker.CircuitBreaker.record_success"),
            patch(
                "src.services.parser.hh_parser_service.HHParserService.parse_vacancies",
                new=AsyncMock(return_value=[]),
            ),
            patch("src.services.progress_service.ProgressService", progress_cls_mock),
            patch("src.services.progress_service.create_progress_redis", return_value=MagicMock()),
            patch(
                "src.services.task_checkpoint.TaskCheckpointService",
                return_value=_make_checkpoint_mock(),
            ),
            patch("src.worker.tasks.autoparse.deliver_autoparse_results"),
        ]

        from contextlib import ExitStack

        with ExitStack() as stack:
            for p in base_patches + _repo_patches(company, user):
                stack.enter_context(p)

            from src.worker.tasks.autoparse import _run_autoparse_company_async

            result = await _run_autoparse_company_async(
                session_factory,
                fake_task,
                company_id=13,
                notify_user_id=None,
            )

        progress_cls_mock.assert_not_called()
        assert result["status"] == "completed"
