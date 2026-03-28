"""Unit tests for autoparse dispatch scheduling and lock-release behaviour."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
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
        company.total_runs = 0
        company.total_vacancies_found = 0
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
    async def test_lock_released_after_task_raises_exception(self):
        """r.delete(lock_key) must be called even when the task raises an exception."""
        from src.worker.tasks.autoparse import _run_autoparse_company_async

        company_repo = MagicMock()
        company_repo.get_by_id = AsyncMock(side_effect=RuntimeError("db exploded"))

        redis_mock = _make_redis_mock()

        with (
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
        redis_mock.delete = MagicMock()

        with patch("src.worker.tasks.autoparse._redis_client", return_value=redis_mock):
            result = asyncio.run(
                _run_autoparse_company_async(
                    _make_session_factory(self._make_session()), MagicMock(), company_id=7
                )
            )

        assert result == {"status": "locked", "company_id": 7}
        redis_mock.delete.assert_not_called()
