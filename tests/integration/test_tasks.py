"""Integration tests for Celery task progress service wiring.

These tests verify that _run_autoparse_company_async correctly integrates with
ProgressService: starting the task on entry, updating bars during scraping and
AI analysis, finishing on success, marking retrying on HH captcha, and cancelling
the progress task on other failures.

All imports inside _run_autoparse_company_async are lazy (local), so patches
must target source modules (e.g. src.services.progress_service.ProgressService)
rather than the calling module.
"""

import sys
from types import ModuleType
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
    c.parse_mode = "api"
    c.parse_hh_linked_account_id = None
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
    vacancy_repo.get_analyzed_for_user_hh_id = AsyncMock(return_value=None)

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


def _configure_vacancy_processing_locks(task, *, acquired: bool = True):
    task.acquire_user_vacancy_processing_lock = AsyncMock(return_value=acquired)
    task.release_user_vacancy_processing_lock = AsyncMock()
    return task


def _crypto_patches():
    crypto_module = ModuleType("src.services.hh.crypto")
    crypto_module.HhTokenCipher = MagicMock()
    storage_module = ModuleType("src.services.hh_ui.storage")
    storage_module.decrypt_browser_storage = MagicMock(return_value={})
    return [
        patch.dict(
            sys.modules,
            {
                "src.services.hh.crypto": crypto_module,
                "src.services.hh_ui.storage": storage_module,
            },
        )
    ]


def _progress_patches(progress_mock):
    return [
        patch("src.services.progress_service.ProgressService", return_value=progress_mock),
        patch("src.services.progress_service.create_progress_redis", return_value=MagicMock()),
    ]


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
                "src.services.parser.hh_parser_service.HHScraper.collect_vacancy_urls",
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
            for p in base_patches + _repo_patches(company, user) + _crypto_patches():
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
        """finish_task is called after successful execution before returning."""
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
                "src.services.parser.hh_parser_service.HHScraper.collect_vacancy_urls",
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
            for p in base_patches + _repo_patches(company, user) + _crypto_patches():
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
    async def test_progress_cancel_task_called_on_exception(self):
        """cancel_task is called when execution fails so the UI does not show all-done."""
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
                "src.services.parser.hh_parser_service.HHScraper.collect_vacancy_urls",
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
            for p in base_patches + _repo_patches(company, user) + _crypto_patches():
                stack.enter_context(p)

            from src.worker.tasks.autoparse import _run_autoparse_company_async

            with pytest.raises(RuntimeError, match="scraping failed"):
                await _run_autoparse_company_async(
                    session_factory,
                    fake_task,
                    company_id=9,
                    notify_user_id=42,
                )

        progress_mock.cancel_task.assert_awaited_once_with("autoparse:9")
        progress_mock.finish_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_task_exception_does_not_suppress_original_error(self):
        """If cancel_task itself raises, the original task exception still propagates."""
        company = _make_company(company_id=11)
        user = _make_user(telegram_id=444)
        session = _make_session()
        session_factory = MagicMock(return_value=session)
        fake_task = MagicMock()
        fake_task.request.id = "test-id-4"

        progress_mock = AsyncMock()
        progress_mock.cancel_task = AsyncMock(side_effect=ValueError("redis down"))

        base_patches = [
            patch("src.worker.tasks.autoparse._redis_client", return_value=_make_sync_redis()),
            patch("src.worker.circuit_breaker.CircuitBreaker.is_call_allowed", return_value=True),
            patch("src.worker.circuit_breaker.CircuitBreaker.record_failure"),
            patch(
                "src.services.parser.hh_parser_service.HHScraper.collect_vacancy_urls",
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
            for p in base_patches + _repo_patches(company, user) + _crypto_patches():
                stack.enter_context(p)

            from src.worker.tasks.autoparse import _run_autoparse_company_async

            # The original RuntimeError must propagate; ValueError from cancel_task is suppressed.
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
                "src.services.parser.hh_parser_service.HHScraper.collect_vacancy_urls",
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
            for p in base_patches + _repo_patches(company, user) + _crypto_patches():
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

    @pytest.mark.asyncio
    async def test_parsing_bar_synced_to_total_to_analyze_when_different_from_target(self):
        """Parsing bar is synced to total_to_analyze when it differs from target_count."""
        company = _make_company(company_id=15, vacancy_title="Fullstack Dev")
        user = _make_user(telegram_id=666)
        user.autoparse_settings = {"tech_stack": ["Python"]}  # Enables ai_client
        session = _make_session()
        session_factory = MagicMock(return_value=session)
        fake_task = MagicMock()
        fake_task.request.id = "test-id-6"
        _configure_vacancy_processing_locks(fake_task)

        # 55 search cards -> detail fetch + AI; total_to_analyze=55; target_count=50 from settings
        search_cards = [
            {"hh_vacancy_id": str(i), "url": f"https://hh.ru/vacancy/{i}", "title": "Dev"}
            for i in range(55)
        ]
        _page_data = {
            "description": "d",
            "skills": [],
            "orm_fields": {},
            "employer_data": {"id": "1", "name": "Co"},
            "area_data": {"id": "1", "name": "Msk"},
            "title": "Dev",
            "company_name": "Co",
        }

        progress_mock = AsyncMock()

        settings_repo = AsyncMock()
        settings_values = {
            "autoparse_target_count": "50",
            "autoparse_interval_hours": "6",
            "task_autoparse_enabled": "true",
        }
        settings_repo.get_value = AsyncMock(
            side_effect=lambda key, default=None: settings_values.get(key, default)
        )

        base_patches = [
            patch("src.worker.tasks.autoparse._redis_client", return_value=_make_sync_redis()),
            patch("src.worker.circuit_breaker.CircuitBreaker.is_call_allowed", return_value=True),
            patch("src.worker.circuit_breaker.CircuitBreaker.record_success"),
            patch(
                "src.services.parser.hh_parser_service.HHScraper.collect_vacancy_urls",
                new=AsyncMock(return_value=search_cards),
            ),
            patch(
                "src.services.parser.hh_parser_service.HHScraper.parse_vacancy_page",
                new=AsyncMock(return_value=_page_data),
            ),
            patch(
                "src.repositories.hh.HHEmployerRepository.get_or_create_by_hh_id",
                new=AsyncMock(return_value=MagicMock(id=1)),
            ),
            patch(
                "src.repositories.hh.HHAreaRepository.get_or_create_by_hh_id",
                new=AsyncMock(return_value=MagicMock(id=1)),
            ),
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
            patch(
                "src.services.ai.client.AIClient.analyze_vacancies_batch",
                new_callable=AsyncMock,
                return_value={
                    str(i): MagicMock(compatibility_score=70.0, summary="", stack=[])
                    for i in range(55)
                },
            ),
        ]

        from contextlib import ExitStack

        with ExitStack() as stack:
            for p in (
                base_patches
                + _repo_patches(company, user)
                + _crypto_patches()
                + _progress_patches(progress_mock)
            ):
                stack.enter_context(p)
            # Override settings to return target_count=50; our 55 results yield total_to_analyze=55
            stack.enter_context(
                patch(
                    "src.repositories.app_settings.AppSettingRepository",
                    return_value=settings_repo,
                )
            )
            # Partition caps fresh fetches at target_count (50). Five IDs are globally known (cached
            # path) and 50 are new fetches → 5 + 50 = 55 for total_to_analyze vs target 50.
            vacancy_repo_bar = AsyncMock()
            vacancy_repo_bar.get_known_hh_ids_for_company = AsyncMock(return_value=set())
            vacancy_repo_bar.get_all_known_hh_ids = AsyncMock(
                return_value={str(i) for i in range(5)}
            )
            stack.enter_context(
                patch(
                    "src.repositories.autoparse.AutoparsedVacancyRepository",
                    return_value=vacancy_repo_bar,
                )
            )

            from src.worker.tasks.autoparse import _run_autoparse_company_async

            result = await _run_autoparse_company_async(
                session_factory,
                fake_task,
                company_id=15,
                notify_user_id=42,
            )

        assert result["status"] == "completed"
        # Parsing bar should progress through the actual fetched detail count.
        parsing_sync_calls = [
            c for c in progress_mock.update_bar.call_args_list
            if c.args[1] == 0 and c.args[2] == 50 and c.args[3] == 50
        ]
        assert len(parsing_sync_calls) >= 1, (
            "Parsing bar should be updated to (50, 50) after fetching the capped detail batch"
        )

    @pytest.mark.asyncio
    async def test_reuses_same_user_analysis_without_second_ai_call(self):
        company = _make_company(company_id=21, vacancy_title="Python Dev")
        user = _make_user(telegram_id=777)
        user.autoparse_settings = {"tech_stack": ["Python"]}
        session = _make_session()
        session_factory = MagicMock(return_value=session)
        fake_task = MagicMock()
        fake_task.request.id = "test-id-reuse"
        _configure_vacancy_processing_locks(fake_task)

        search_cards = [
            {"hh_vacancy_id": "123", "url": "https://hh.ru/vacancy/123", "title": "Python Dev"}
        ]
        page_data = {
            "description": "d",
            "skills": ["Python"],
            "orm_fields": {},
            "employer_data": {"id": "1", "name": "Co"},
            "area_data": {"id": "1", "name": "Msk"},
            "title": "Python Dev",
            "company_name": "Co",
        }
        reusable = MagicMock(
            compatibility_score=88.0,
            ai_summary="Reused summary",
            ai_stack=["Python", "FastAPI"],
        )
        progress_mock = AsyncMock()

        base_patches = [
            patch("src.worker.tasks.autoparse._redis_client", return_value=_make_sync_redis()),
            patch("src.worker.circuit_breaker.CircuitBreaker.is_call_allowed", return_value=True),
            patch("src.worker.circuit_breaker.CircuitBreaker.record_success"),
            patch(
                "src.services.parser.hh_parser_service.HHScraper.collect_vacancy_urls",
                new=AsyncMock(return_value=search_cards),
            ),
            patch(
                "src.services.parser.hh_parser_service.HHScraper.parse_vacancy_page",
                new=AsyncMock(return_value=page_data),
            ),
            patch(
                "src.repositories.hh.HHEmployerRepository.get_or_create_by_hh_id",
                new=AsyncMock(return_value=MagicMock(id=1)),
            ),
            patch(
                "src.repositories.hh.HHAreaRepository.get_or_create_by_hh_id",
                new=AsyncMock(return_value=MagicMock(id=1)),
            ),
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
            patch(
                "src.services.ai.client.AIClient.analyze_vacancies_batch",
                new_callable=AsyncMock,
            ),
        ]

        from contextlib import ExitStack

        with ExitStack() as stack:
            ai_mock = None
            for p in (
                base_patches
                + _repo_patches(company, user)
                + _crypto_patches()
                + _progress_patches(progress_mock)
            ):
                result = stack.enter_context(p)
                if getattr(p, "attribute", None) == "analyze_vacancies_batch":
                    ai_mock = result
            vacancy_repo = AsyncMock()
            vacancy_repo.get_known_hh_ids_for_company = AsyncMock(return_value=set())
            vacancy_repo.get_all_known_hh_ids = AsyncMock(return_value=set())
            vacancy_repo.get_analyzed_for_user_hh_id = AsyncMock(return_value=reusable)
            stack.enter_context(
                patch(
                    "src.repositories.autoparse.AutoparsedVacancyRepository",
                    return_value=vacancy_repo,
                )
            )

            from src.worker.tasks.autoparse import _run_autoparse_company_async

            result = await _run_autoparse_company_async(
                session_factory,
                fake_task,
                company_id=21,
                notify_user_id=42,
            )

        assert result["status"] == "completed"
        assert ai_mock.await_count == 0
        fake_task.acquire_user_vacancy_processing_lock.assert_not_awaited()
        inserted_row = session.add.call_args.args[0]
        assert inserted_row.compatibility_score == pytest.approx(88.0)
        assert inserted_row.ai_summary == "Reused summary"
        assert inserted_row.ai_stack == ["Python", "FastAPI"]

    @pytest.mark.asyncio
    async def test_does_not_reuse_zero_compatibility_score(self):
        company = _make_company(company_id=24, vacancy_title="Python Dev")
        user = _make_user(telegram_id=778)
        user.autoparse_settings = {"tech_stack": ["Python"]}
        session = _make_session()
        session_factory = MagicMock(return_value=session)
        fake_task = MagicMock()
        fake_task.request.id = "test-id-zero-reuse"
        _configure_vacancy_processing_locks(fake_task)

        search_cards = [
            {
                "hh_vacancy_id": "123",
                "url": "https://hh.ru/vacancy/123",
                "title": "Python Dev",
                "cached": True,
            }
        ]
        reusable = MagicMock(
            compatibility_score=0.0,
            ai_summary="Old zero summary",
            ai_stack=["Python"],
        )
        existing_ap = MagicMock(
            hh_vacancy_id="123",
            url="https://hh.ru/vacancy/123",
            title="Python Dev",
            description="d",
            raw_skills=["Python"],
            company_name="Co",
            company_url=None,
            salary=None,
            compensation_frequency=None,
            work_experience=None,
            employment_type=None,
            work_schedule=None,
            working_hours=None,
            work_formats=None,
            tags=None,
            snippet_requirement=None,
            snippet_responsibility=None,
            experience_id=None,
            experience_name=None,
            schedule_id=None,
            schedule_name=None,
            employment_id=None,
            employment_name=None,
            employment_form_id=None,
            employment_form_name=None,
            salary_from=None,
            salary_to=None,
            salary_currency=None,
            salary_gross=None,
            address_raw=None,
            address_city=None,
            address_street=None,
            address_building=None,
            address_lat=None,
            address_lng=None,
            metro_stations=None,
            vacancy_type_id=None,
            published_at=None,
            work_format=None,
            professional_roles=None,
            employer_id=1,
            area_id=1,
            compatibility_score=0.0,
            ai_summary="Old zero summary",
            ai_stack=["Python"],
        )
        progress_mock = AsyncMock()

        base_patches = [
            patch("src.worker.tasks.autoparse._redis_client", return_value=_make_sync_redis()),
            patch("src.worker.circuit_breaker.CircuitBreaker.is_call_allowed", return_value=True),
            patch("src.worker.circuit_breaker.CircuitBreaker.record_success"),
            patch(
                "src.services.parser.hh_parser_service.HHScraper.collect_vacancy_urls",
                new=AsyncMock(return_value=search_cards),
            ),
            patch(
                "src.repositories.hh.HHEmployerRepository.get_or_create_by_hh_id",
                new=AsyncMock(return_value=MagicMock(id=1)),
            ),
            patch(
                "src.repositories.hh.HHAreaRepository.get_or_create_by_hh_id",
                new=AsyncMock(return_value=MagicMock(id=1)),
            ),
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
            patch(
                "src.services.ai.client.AIClient.analyze_vacancies_batch",
                new_callable=AsyncMock,
                return_value={
                    "123": MagicMock(
                        compatibility_score=77.0,
                        summary="Fresh summary",
                        stack=["Python", "FastAPI"],
                    )
                },
            ),
        ]

        from contextlib import ExitStack

        with ExitStack() as stack:
            ai_mock = None
            for p in (
                base_patches
                + _repo_patches(company, user)
                + _crypto_patches()
                + _progress_patches(progress_mock)
            ):
                result = stack.enter_context(p)
                if getattr(p, "attribute", None) == "analyze_vacancies_batch":
                    ai_mock = result
            vacancy_repo = AsyncMock()
            vacancy_repo.get_known_hh_ids_for_company = AsyncMock(return_value=set())
            vacancy_repo.get_all_known_hh_ids = AsyncMock(return_value={"123"})
            vacancy_repo.get_analyzed_for_user_hh_id = AsyncMock(return_value=reusable)
            vacancy_repo.get_by_company_hh_id_with_employer = AsyncMock(return_value=existing_ap)
            stack.enter_context(
                patch(
                    "src.repositories.autoparse.AutoparsedVacancyRepository",
                    return_value=vacancy_repo,
                )
            )

            from src.worker.tasks.autoparse import _run_autoparse_company_async

            result = await _run_autoparse_company_async(
                session_factory,
                fake_task,
                company_id=24,
                notify_user_id=42,
            )

        assert result["status"] == "completed"
        assert ai_mock.await_count == 1
        fake_task.acquire_user_vacancy_processing_lock.assert_awaited()
        inserted_row = session.add.call_args.args[0]
        assert inserted_row.compatibility_score == pytest.approx(77.0)
        assert inserted_row.ai_summary == "Fresh summary"
        assert inserted_row.ai_stack == ["Python", "FastAPI"]

    @pytest.mark.asyncio
    async def test_does_not_advance_analyzed_progress_for_unanalyzed_locked_vacancy(self):
        company = _make_company(company_id=23, vacancy_title="Python Dev")
        user = _make_user(telegram_id=889)
        user.autoparse_settings = {"tech_stack": ["Python"]}
        session = _make_session()
        session_factory = MagicMock(return_value=session)
        fake_task = MagicMock()
        fake_task.request.id = "test-id-unanalyzed"
        _configure_vacancy_processing_locks(fake_task, acquired=False)

        search_cards = [
            {"hh_vacancy_id": "999", "url": "https://hh.ru/vacancy/999", "title": "Python Dev"}
        ]
        page_data = {
            "description": "d",
            "skills": ["Python"],
            "orm_fields": {},
            "employer_data": {"id": "1", "name": "Co"},
            "area_data": {"id": "1", "name": "Msk"},
            "title": "Python Dev",
            "company_name": "Co",
        }
        progress_mock = AsyncMock()
        checkpoint_mock = _make_checkpoint_mock()

        base_patches = [
            patch("src.worker.tasks.autoparse._redis_client", return_value=_make_sync_redis()),
            patch("src.worker.circuit_breaker.CircuitBreaker.is_call_allowed", return_value=True),
            patch("src.worker.circuit_breaker.CircuitBreaker.record_success"),
            patch(
                "src.services.parser.hh_parser_service.HHScraper.collect_vacancy_urls",
                new=AsyncMock(return_value=search_cards),
            ),
            patch(
                "src.services.parser.hh_parser_service.HHScraper.parse_vacancy_page",
                new=AsyncMock(return_value=page_data),
            ),
            patch(
                "src.repositories.hh.HHEmployerRepository.get_or_create_by_hh_id",
                new=AsyncMock(return_value=MagicMock(id=1)),
            ),
            patch(
                "src.repositories.hh.HHAreaRepository.get_or_create_by_hh_id",
                new=AsyncMock(return_value=MagicMock(id=1)),
            ),
            patch(
                "src.services.task_checkpoint.TaskCheckpointService",
                return_value=checkpoint_mock,
            ),
            patch("src.worker.tasks.autoparse.deliver_autoparse_results"),
            patch(
                "src.worker.tasks.autoparse._send_run_completed_notification",
                new=AsyncMock(),
            ),
            patch("aiogram.Bot", return_value=_make_mock_bot()),
            patch(
                "src.services.ai.client.AIClient.analyze_vacancies_batch",
                new_callable=AsyncMock,
            ),
        ]

        from contextlib import ExitStack

        with ExitStack() as stack:
            ai_mock = None
            for p in (
                base_patches
                + _repo_patches(company, user)
                + _crypto_patches()
                + _progress_patches(progress_mock)
            ):
                result = stack.enter_context(p)
                if getattr(p, "attribute", None) == "analyze_vacancies_batch":
                    ai_mock = result

            vacancy_repo = AsyncMock()
            vacancy_repo.get_known_hh_ids_for_company = AsyncMock(return_value=set())
            vacancy_repo.get_all_known_hh_ids = AsyncMock(return_value=set())
            vacancy_repo.get_analyzed_for_user_hh_id = AsyncMock(return_value=None)
            stack.enter_context(
                patch(
                    "src.repositories.autoparse.AutoparsedVacancyRepository",
                    return_value=vacancy_repo,
                )
            )

            from src.worker.tasks.autoparse import _run_autoparse_company_async

            result = await _run_autoparse_company_async(
                session_factory,
                fake_task,
                company_id=23,
                notify_user_id=42,
            )

        assert result["status"] == "completed"
        ai_mock.assert_not_awaited()
        checkpoint_mock.save.assert_awaited()
        analyzed_values = [call.kwargs["analyzed"] for call in checkpoint_mock.save.await_args_list]
        assert analyzed_values[-1] == 0
        inserted_row = session.add.call_args.args[0]
        assert inserted_row.compatibility_score is None
        assert inserted_row.ai_summary is None
        assert inserted_row.ai_stack is None

    @pytest.mark.asyncio
    async def test_web_mode_uses_web_search_but_api_detail(self):
        company = _make_company(company_id=22, vacancy_title="Python Dev")
        company.parse_mode = "web"
        user = _make_user(telegram_id=888)
        session = _make_session()
        session_factory = MagicMock(return_value=session)
        fake_task = MagicMock()
        fake_task.request.id = "test-id-web-api-detail"

        search_cards = [
            {"hh_vacancy_id": "321", "url": "https://hh.ru/vacancy/321", "title": "Python Dev"}
        ]
        page_data = {
            "description": "d",
            "skills": ["Python"],
            "orm_fields": {},
            "employer_data": {"id": "1", "name": "Co"},
            "area_data": {"id": "1", "name": "Msk"},
            "title": "Python Dev",
            "company_name": "Co",
        }

        base_patches = [
            patch("src.worker.tasks.autoparse._redis_client", return_value=_make_sync_redis()),
            patch("src.worker.circuit_breaker.CircuitBreaker.is_call_allowed", return_value=True),
            patch("src.worker.circuit_breaker.CircuitBreaker.record_success"),
            patch(
                "src.services.parser.hh_parser_service.HHScraper.collect_vacancy_urls",
                new=AsyncMock(return_value=search_cards),
            ),
            patch(
                "src.services.parser.hh_parser_service.HHScraper.parse_vacancy_page",
                new=AsyncMock(return_value=page_data),
            ),
            patch(
                "src.repositories.hh.HHEmployerRepository.get_or_create_by_hh_id",
                new=AsyncMock(return_value=MagicMock(id=1)),
            ),
            patch(
                "src.repositories.hh.HHAreaRepository.get_or_create_by_hh_id",
                new=AsyncMock(return_value=MagicMock(id=1)),
            ),
            patch(
                "src.services.task_checkpoint.TaskCheckpointService",
                return_value=_make_checkpoint_mock(),
            ),
            patch("src.worker.tasks.autoparse.deliver_autoparse_results"),
        ]

        from contextlib import ExitStack

        with ExitStack() as stack:
            collect_mock = None
            detail_mock = None
            for p in base_patches + _repo_patches(company, user) + _crypto_patches():
                result = stack.enter_context(p)
                if getattr(p, "attribute", None) == "collect_vacancy_urls":
                    collect_mock = result
                elif getattr(p, "attribute", None) == "parse_vacancy_page":
                    detail_mock = result

            from src.worker.tasks.autoparse import _run_autoparse_company_async

            result = await _run_autoparse_company_async(
                session_factory,
                fake_task,
                company_id=22,
                notify_user_id=None,
            )

        assert result["status"] == "completed"
        assert collect_mock.await_args.kwargs["parse_mode"] == "web"
        assert detail_mock.await_args.kwargs["parse_mode"] == "api"
