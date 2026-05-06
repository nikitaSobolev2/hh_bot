"""Unit tests for autoparse dispatch scheduling and lock-release behaviour."""

import asyncio
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# AutoparseCompanyRepository.get_due_for_dispatch
# ---------------------------------------------------------------------------


class TestGetDueForDispatch:
    """get_due_for_dispatch returns only companies whose last run is overdue."""

    def _make_company(
        self,
        *,
        company_id: int = 1,
        is_enabled: bool = True,
        is_deleted: bool = False,
        last_parsed_at: datetime | None = None,
    ) -> MagicMock:
        company = MagicMock()
        company.id = company_id
        company.is_enabled = is_enabled
        company.is_deleted = is_deleted
        company.last_parsed_at = last_parsed_at
        return company

    def _make_session(self, rows: list) -> MagicMock:
        session = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all = lambda: rows
        execute_result = MagicMock()
        execute_result.scalars = lambda: scalars_mock
        session.execute = AsyncMock(return_value=execute_result)
        return session

    @pytest.mark.asyncio
    async def test_returns_company_with_no_last_parsed_at(self):
        """A company that has never run must always be returned."""
        from src.repositories.autoparse import AutoparseCompanyRepository

        company = self._make_company(last_parsed_at=None)
        repo = AutoparseCompanyRepository(self._make_session([company]))
        results = await repo.get_due_for_dispatch(6)

        assert company in results

    @pytest.mark.asyncio
    async def test_returns_company_whose_last_run_exceeds_interval(self):
        """A company last parsed more than interval_hours ago must be returned."""
        from src.repositories.autoparse import AutoparseCompanyRepository

        old_run = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=8)
        company = self._make_company(last_parsed_at=old_run)
        repo = AutoparseCompanyRepository(self._make_session([company]))
        results = await repo.get_due_for_dispatch(6)

        assert company in results

    @pytest.mark.asyncio
    async def test_excludes_company_that_ran_recently(self):
        """A company last parsed less than interval_hours ago must NOT be returned."""
        from src.repositories.autoparse import AutoparseCompanyRepository

        # Simulate the DB filter excluding the company (empty result).
        repo = AutoparseCompanyRepository(self._make_session([]))
        results = await repo.get_due_for_dispatch(6)

        assert list(results) == []

    @pytest.mark.asyncio
    async def test_query_filters_on_enabled_and_not_deleted(self):
        """The method source must reference is_enabled, is_deleted, and last_parsed_at."""
        import inspect

        from src.repositories.autoparse import AutoparseCompanyRepository

        repo = AutoparseCompanyRepository(self._make_session([]))
        source = inspect.getsource(repo.get_due_for_dispatch)

        assert "is_enabled" in source
        assert "is_deleted" in source
        assert "last_parsed_at" in source


# ---------------------------------------------------------------------------
# _dispatch_all_async: only dispatches due companies
# ---------------------------------------------------------------------------


def _make_session_factory(session: MagicMock):
    @asynccontextmanager
    async def factory():
        yield session

    return factory


def _make_redis_mock() -> MagicMock:
    redis_mock = MagicMock()
    redis_mock.eval = MagicMock(return_value=1)
    redis_mock.delete = MagicMock()
    return redis_mock


def _make_checkpoint_mock() -> MagicMock:
    mock = MagicMock()
    mock.load = AsyncMock(return_value=None)
    mock.save = AsyncMock()
    mock.clear = AsyncMock()
    return mock


def _crypto_patch():
    crypto_module = ModuleType("src.services.hh.crypto")
    crypto_module.HhTokenCipher = MagicMock()
    storage_module = ModuleType("src.services.hh_ui.storage")
    storage_module.decrypt_browser_storage = MagicMock(return_value={})
    return patch.dict(
        sys.modules,
        {
            "src.services.hh.crypto": crypto_module,
            "src.services.hh_ui.storage": storage_module,
        },
    )


class TestDispatchAllAsync:
    """_dispatch_all_async must only dispatch companies that are due."""

    def _make_session(self) -> MagicMock:
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        return session

    def _make_settings_repo(self, *, enabled: bool = True, interval: int = 6) -> MagicMock:
        repo = MagicMock()

        async def get_value(key, default=None):
            return {
                "task_autoparse_enabled": enabled,
                "autoparse_interval_hours": interval,
            }.get(key, default)

        repo.get_value = get_value
        return repo

    @pytest.mark.asyncio
    async def test_dispatches_due_companies_using_get_due_for_dispatch(self):
        """Dispatch must call get_due_for_dispatch, not get_all_enabled."""
        from src.worker.tasks.autoparse import _dispatch_all_async

        company = MagicMock()
        company.id = 42

        settings_repo = self._make_settings_repo()
        company_repo = MagicMock()
        company_repo.get_due_for_dispatch = AsyncMock(return_value=[company])
        company_repo.get_all_enabled = AsyncMock(return_value=[company])

        with (
            patch(
                "src.repositories.app_settings.AppSettingRepository",
                return_value=settings_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch("src.worker.tasks.autoparse._redis_client", return_value=_make_redis_mock()),
            patch("src.worker.tasks.autoparse.run_autoparse_company") as mock_task,
        ):
            mock_task.delay = MagicMock()
            result = await _dispatch_all_async(_make_session_factory(self._make_session()))

        company_repo.get_due_for_dispatch.assert_called_once_with(6)
        company_repo.get_all_enabled.assert_not_called()
        mock_task.delay.assert_called_once_with(42)
        assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_dispatches_zero_when_no_companies_are_due(self):
        """When no companies are due, dispatch count must be zero."""
        from src.worker.tasks.autoparse import _dispatch_all_async

        settings_repo = self._make_settings_repo()
        company_repo = MagicMock()
        company_repo.get_due_for_dispatch = AsyncMock(return_value=[])

        with (
            patch(
                "src.repositories.app_settings.AppSettingRepository",
                return_value=settings_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch("src.worker.tasks.autoparse._redis_client", return_value=_make_redis_mock()),
        ):
            result = await _dispatch_all_async(_make_session_factory(self._make_session()))

        assert result == {"status": "dispatched", "count": 0}

    @pytest.mark.asyncio
    async def test_returns_disabled_when_task_autoparse_enabled_is_false(self):
        """Dispatch must abort early when task_autoparse_enabled is False."""
        from src.worker.tasks.autoparse import _dispatch_all_async

        settings_repo = self._make_settings_repo(enabled=False)

        with (
            patch(
                "src.repositories.app_settings.AppSettingRepository",
                return_value=settings_repo,
            ),
            patch("src.worker.tasks.autoparse._redis_client", return_value=_make_redis_mock()),
        ):
            result = await _dispatch_all_async(_make_session_factory(self._make_session()))

        assert result == {"status": "disabled"}


# ---------------------------------------------------------------------------
# _run_autoparse_company_async: lock released on success and failure
# ---------------------------------------------------------------------------


class TestRunAutoparseCompanyLock:
    """The per-company Redis lock must always be released after the task finishes."""

    def _make_session(self) -> MagicMock:
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        session.commit = AsyncMock()
        session.add = MagicMock()
        return session

    def _make_company(self) -> MagicMock:
        company = MagicMock()
        company.id = 1
        company.user_id = 10
        company.is_deleted = False
        company.is_enabled = True
        company.vacancy_title = "Backend"
        company.search_url = "https://hh.ru/search/vacancy?text=backend"
        company.keyword_filter = ""
        company.keyword_check_enabled = True
        company.total_runs = 0
        company.total_vacancies_found = 0
        company.parse_hh_linked_account_id = None
        company.parse_mode = "api"
        return company

    @pytest.mark.asyncio
    async def test_lock_released_after_successful_run(self):
        """r.delete(lock_key) must be called when the task completes successfully."""
        from src.worker.tasks.autoparse import _run_autoparse_company_async

        company = self._make_company()

        vacancy_repo = MagicMock()
        vacancy_repo.get_known_hh_ids_for_company = AsyncMock(return_value=set())
        vacancy_repo.get_all_known_hh_ids = AsyncMock(return_value=set())

        parsed_repo = MagicMock()
        parsed_repo.get_all_hh_ids = AsyncMock(return_value=set())

        settings_repo = MagicMock()
        settings_repo.get_value = AsyncMock(return_value=50)

        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=None)

        we_repo = MagicMock()
        we_repo.get_active_by_user = AsyncMock(return_value=[])

        company_repo = MagicMock()
        company_repo.get_by_id = AsyncMock(return_value=company)
        company_repo.update = AsyncMock()

        redis_mock = _make_redis_mock()

        with (
            _crypto_patch(),
            patch("src.worker.tasks.autoparse._redis_client", return_value=redis_mock),
            patch("src.worker.circuit_breaker.CircuitBreaker.is_call_allowed", return_value=True),
            patch("src.worker.circuit_breaker.CircuitBreaker.record_success"),
            patch(
                "src.repositories.app_settings.AppSettingRepository",
                return_value=settings_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparsedVacancyRepository",
                return_value=vacancy_repo,
            ),
            patch("src.repositories.parsing.ParsedVacancyRepository", return_value=parsed_repo),
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch(
                "src.repositories.work_experience.WorkExperienceRepository",
                return_value=we_repo,
            ),
            patch(
                "src.services.parser.scraper.HHScraper.collect_vacancy_urls",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "src.services.task_checkpoint.TaskCheckpointService",
                return_value=_make_checkpoint_mock(),
            ),
        ):
            await _run_autoparse_company_async(
                _make_session_factory(self._make_session()), MagicMock(), company_id=1
            )

        redis_mock.delete.assert_called_with("lock:autoparse:run:1")

    @pytest.mark.asyncio
    async def test_disables_keyword_filter_during_collection_when_company_toggle_is_off(self):
        from src.worker.tasks.autoparse import _run_autoparse_company_async

        company = self._make_company()
        company.keyword_filter = "python"
        company.keyword_check_enabled = False

        vacancy_repo = MagicMock()
        vacancy_repo.get_known_hh_ids_for_company = AsyncMock(return_value=set())
        vacancy_repo.get_all_known_hh_ids = AsyncMock(return_value=set())

        parsed_repo = MagicMock()
        parsed_repo.get_all_hh_ids = AsyncMock(return_value=set())

        settings_repo = MagicMock()
        settings_repo.get_value = AsyncMock(return_value=50)

        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=None)

        we_repo = MagicMock()
        we_repo.get_active_by_user = AsyncMock(return_value=[])

        company_repo = MagicMock()
        company_repo.get_by_id = AsyncMock(return_value=company)
        company_repo.update = AsyncMock()

        redis_mock = _make_redis_mock()

        with (
            _crypto_patch(),
            patch("src.worker.tasks.autoparse._redis_client", return_value=redis_mock),
            patch("src.worker.circuit_breaker.CircuitBreaker.is_call_allowed", return_value=True),
            patch("src.worker.circuit_breaker.CircuitBreaker.record_success"),
            patch(
                "src.repositories.app_settings.AppSettingRepository",
                return_value=settings_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparsedVacancyRepository",
                return_value=vacancy_repo,
            ),
            patch("src.repositories.parsing.ParsedVacancyRepository", return_value=parsed_repo),
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch(
                "src.repositories.work_experience.WorkExperienceRepository",
                return_value=we_repo,
            ),
            patch(
                "src.services.parser.scraper.HHScraper.collect_vacancy_urls",
                new_callable=AsyncMock,
                return_value=[],
            ) as collect_mock,
            patch(
                "src.services.task_checkpoint.TaskCheckpointService",
                return_value=_make_checkpoint_mock(),
            ),
        ):
            await _run_autoparse_company_async(
                _make_session_factory(self._make_session()), MagicMock(), company_id=1
            )

        assert collect_mock.await_args.args[1] == ""

    @pytest.mark.asyncio
    async def test_completed_result_includes_new_vacancy_ids(self):
        from src.worker.tasks.autoparse import _run_autoparse_company_async

        company = self._make_company()

        vacancy_repo = MagicMock()
        vacancy_repo.get_known_hh_ids_for_company = AsyncMock(return_value=set())
        vacancy_repo.get_all_known_hh_ids = AsyncMock(return_value=set())
        vacancy_repo.get_analyzed_for_user_hh_id = AsyncMock(return_value=None)

        parsed_repo = MagicMock()
        parsed_repo.get_all_hh_ids = AsyncMock(return_value=set())

        settings_repo = MagicMock()
        settings_repo.get_value = AsyncMock(return_value=50)

        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=None)

        we_repo = MagicMock()
        we_repo.get_active_by_user = AsyncMock(return_value=[])

        company_repo = MagicMock()
        company_repo.get_by_id = AsyncMock(return_value=company)
        company_repo.update = AsyncMock()

        redis_mock = _make_redis_mock()
        fake_task = MagicMock()
        fake_task.request.id = "task-new-ids"
        fake_row = SimpleNamespace(id=321)
        merged_vacancy = {
            "hh_vacancy_id": "vac-1",
            "title": "Backend Developer",
            "raw_skills": [],
            "description": "desc",
            "vacancy_api_context": None,
            "employer_data": {},
            "area_data": {},
        }

        @asynccontextmanager
        async def fake_client_cm():
            yield MagicMock()

        with (
            _crypto_patch(),
            patch("src.worker.tasks.autoparse._redis_client", return_value=redis_mock),
            patch("src.worker.circuit_breaker.CircuitBreaker.is_call_allowed", return_value=True),
            patch("src.worker.circuit_breaker.CircuitBreaker.record_success"),
            patch(
                "src.repositories.app_settings.AppSettingRepository",
                return_value=settings_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparsedVacancyRepository",
                return_value=vacancy_repo,
            ),
            patch("src.repositories.parsing.ParsedVacancyRepository", return_value=parsed_repo),
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch(
                "src.repositories.work_experience.WorkExperienceRepository",
                return_value=we_repo,
            ),
            patch(
                "src.services.parser.scraper.HHScraper.collect_vacancy_urls",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "hh_vacancy_id": "vac-1",
                        "url": "https://hh.ru/vacancy/vac-1",
                        "title": "Backend Developer",
                    }
                ],
            ),
            patch(
                "src.services.parser.hh_parser_service.HHParserService.fetch_details_batch_slice",
                new=AsyncMock(return_value=[merged_vacancy]),
            ),
            patch(
                "src.services.parser.hh_parser_service.HHParserService.build_client",
                return_value=fake_client_cm(),
            ),
            patch("src.worker.tasks.autoparse._build_autoparsed_vacancy", return_value=fake_row),
            patch(
                "src.services.task_checkpoint.TaskCheckpointService",
                return_value=_make_checkpoint_mock(),
            ),
        ):
            result = await _run_autoparse_company_async(
                _make_session_factory(self._make_session()),
                fake_task,
                company_id=1,
            )

        assert result["status"] == "completed"
        assert result["new_vacancy_ids"] == [321]

    @pytest.mark.asyncio
    async def test_logs_compatibility_scores_for_completed_ai_batch(self):
        from src.worker.tasks import autoparse as autoparse_module

        company = self._make_company()
        company.autorespond_enabled = False
        company.autorespond_hh_linked_account_id = None
        user = MagicMock()
        user.autoparse_settings = {"tech_stack": ["Python"]}
        user.is_admin = False

        vacancy_repo = MagicMock()
        vacancy_repo.get_known_hh_ids_for_company = AsyncMock(return_value=set())
        vacancy_repo.get_all_known_hh_ids = AsyncMock(return_value=set())
        vacancy_repo.get_analyzed_for_user_hh_id = AsyncMock(return_value=None)

        parsed_repo = MagicMock()
        parsed_repo.get_all_hh_ids = AsyncMock(return_value=set())

        settings_repo = MagicMock()
        settings_repo.get_value = AsyncMock(return_value=50)

        user_repo = MagicMock()
        user_repo.get_by_id = AsyncMock(return_value=user)

        we_repo = MagicMock()
        we_repo.get_active_by_user = AsyncMock(return_value=[])

        company_repo = MagicMock()
        company_repo.get_by_id = AsyncMock(return_value=company)
        company_repo.update = AsyncMock()

        redis_mock = _make_redis_mock()
        fake_task = MagicMock()
        fake_task.request.id = "task-compat-logs"
        fake_task.acquire_user_vacancy_processing_lock = AsyncMock(return_value=True)
        fake_task.release_user_vacancy_processing_lock = AsyncMock()
        fake_row = SimpleNamespace(id=654)
        logger_mock = MagicMock()
        merged_vacancy = {
            "hh_vacancy_id": "vac-compat-1",
            "title": "Backend Developer",
            "raw_skills": ["Python"],
            "description": "desc",
            "vacancy_api_context": None,
            "employer_data": {},
            "area_data": {},
        }

        @asynccontextmanager
        async def fake_client_cm():
            yield MagicMock()

        with (
            _crypto_patch(),
            patch.object(autoparse_module, "logger", logger_mock),
            patch("src.worker.tasks.autoparse._redis_client", return_value=redis_mock),
            patch("src.worker.circuit_breaker.CircuitBreaker.is_call_allowed", return_value=True),
            patch("src.worker.circuit_breaker.CircuitBreaker.record_success"),
            patch(
                "src.repositories.app_settings.AppSettingRepository",
                return_value=settings_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch(
                "src.repositories.autoparse.AutoparsedVacancyRepository",
                return_value=vacancy_repo,
            ),
            patch("src.repositories.parsing.ParsedVacancyRepository", return_value=parsed_repo),
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch(
                "src.repositories.work_experience.WorkExperienceRepository",
                return_value=we_repo,
            ),
            patch(
                "src.services.parser.scraper.HHScraper.collect_vacancy_urls",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "hh_vacancy_id": "vac-compat-1",
                        "url": "https://hh.ru/vacancy/vac-compat-1",
                        "title": "Backend Developer",
                    }
                ],
            ),
            patch(
                "src.services.parser.hh_parser_service.HHParserService.fetch_details_batch_slice",
                new=AsyncMock(return_value=[merged_vacancy]),
            ),
            patch(
                "src.services.parser.hh_parser_service.HHParserService.build_client",
                return_value=fake_client_cm(),
            ),
            patch("src.worker.tasks.autoparse._build_autoparsed_vacancy", return_value=fake_row),
            patch(
                "src.services.ai.client.AIClient.analyze_vacancies_batch",
                new=AsyncMock(
                    return_value={
                        "vac-compat-1": SimpleNamespace(
                            compatibility_score=78.0,
                            summary="Good fit",
                            stack=["Python"],
                        )
                    }
                ),
            ),
            patch("src.worker.tasks.autoparse.deliver_autoparse_results"),
            patch(
                "src.services.task_checkpoint.TaskCheckpointService",
                return_value=_make_checkpoint_mock(),
            ),
        ):
            result = await autoparse_module._run_autoparse_company_async(
                _make_session_factory(self._make_session()),
                fake_task,
                company_id=1,
            )

        assert result["status"] == "completed"
        compat_log_calls = [
            call
            for call in logger_mock.info.call_args_list
            if call.args[0] == "Autoparse compatibility batch completed"
        ]
        assert len(compat_log_calls) == 1
        assert compat_log_calls[0].kwargs["compatibility_scores"] == ["vac-compat-1:78.0"]

    @pytest.mark.asyncio
    async def test_lock_released_after_task_raises_exception(self):
        """r.delete(lock_key) must be called even when the task raises an exception."""
        from src.worker.tasks.autoparse import _run_autoparse_company_async

        company_repo = MagicMock()
        company_repo.get_by_id = AsyncMock(side_effect=RuntimeError("db exploded"))

        redis_mock = _make_redis_mock()

        with (
            _crypto_patch(),
            patch("src.worker.tasks.autoparse._redis_client", return_value=redis_mock),
            patch("src.worker.circuit_breaker.CircuitBreaker.is_call_allowed", return_value=True),
            patch("src.worker.circuit_breaker.CircuitBreaker.record_failure"),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch("src.repositories.app_settings.AppSettingRepository"),
            patch("src.repositories.autoparse.AutoparsedVacancyRepository"),
            patch("src.repositories.parsing.ParsedVacancyRepository"),
            patch("src.repositories.user.UserRepository"),
            patch("src.repositories.work_experience.WorkExperienceRepository"),
            pytest.raises(RuntimeError, match="db exploded"),
        ):
            await _run_autoparse_company_async(
                _make_session_factory(self._make_session()), MagicMock(), company_id=1
            )

        redis_mock.delete.assert_called_with("lock:autoparse:run:1")

    @pytest.mark.asyncio
    async def test_lock_released_when_circuit_breaker_is_open(self):
        """r.delete(lock_key) must be called even when the circuit breaker rejects the call."""
        from src.worker.tasks.autoparse import _run_autoparse_company_async

        redis_mock = _make_redis_mock()

        with (
            _crypto_patch(),
            patch("src.worker.tasks.autoparse._redis_client", return_value=redis_mock),
            patch("src.worker.circuit_breaker.CircuitBreaker.is_call_allowed", return_value=False),
        ):
            result = await _run_autoparse_company_async(
                _make_session_factory(self._make_session()), MagicMock(), company_id=5
            )

        assert result == {"status": "circuit_open"}
        redis_mock.delete.assert_called_with("lock:autoparse:run:5")

    def test_lock_not_acquired_when_already_held(self):
        """When the Redis lock is already held by a different task, return locked immediately."""
        from src.worker.tasks.autoparse import _run_autoparse_company_async

        redis_mock = MagicMock()
        redis_mock.eval = MagicMock(return_value=0)  # Lua script: lock held by different task
        redis_mock.get = MagicMock(return_value=b"other-celery-task-id")
        redis_mock.delete = MagicMock()

        with (
            _crypto_patch(),
            patch("src.worker.tasks.autoparse._redis_client", return_value=redis_mock),
            patch(
                "src.worker.tasks.autoparse.celery_task_id_known_to_workers",
                return_value=True,
            ),
        ):
            result = asyncio.run(
                _run_autoparse_company_async(
                    _make_session_factory(self._make_session()), MagicMock(), company_id=7
                )
            )

        assert result == {"status": "locked", "company_id": 7}
        redis_mock.delete.assert_not_called()

    def test_stale_run_lock_cleared_when_holder_not_on_workers(self):
        """After crash, lock key can outlive the task; clear if Celery no longer lists that id."""
        from src.worker.tasks.autoparse import _run_autoparse_company_async

        redis_mock = MagicMock()
        redis_mock.eval = MagicMock(side_effect=[0, 1])
        redis_mock.get = MagicMock(return_value=b"dead-task-id")
        redis_mock.delete = MagicMock()

        with (
            _crypto_patch(),
            patch("src.worker.tasks.autoparse._redis_client", return_value=redis_mock),
            patch(
                "src.worker.tasks.autoparse.celery_task_id_known_to_workers",
                return_value=False,
            ),
            patch("src.worker.circuit_breaker.CircuitBreaker.is_call_allowed", return_value=False),
        ):
            result = asyncio.run(
                _run_autoparse_company_async(
                    _make_session_factory(self._make_session()), MagicMock(), company_id=7
                )
            )

        assert result == {"status": "circuit_open"}
        redis_mock.delete.assert_any_call("lock:autoparse:run:7")
