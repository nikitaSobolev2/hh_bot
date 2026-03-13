"""Tests for the batch compatibility filter and extractor integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# ParsingExtractor.run_pipeline with compat_params (batch compat)
# ---------------------------------------------------------------------------


def _make_page_data(description: str = "desc", skills: list | None = None) -> dict:
    return {"description": description, "skills": skills or []}


def _make_scraper(page_data: dict | None = None):
    scraper = MagicMock()
    scraper.collect_vacancy_urls = AsyncMock(
        return_value=[
            {"title": "Backend Dev", "url": "https://hh.ru/1", "hh_vacancy_id": "1"},
            {"title": "Java Dev", "url": "https://hh.ru/2", "hh_vacancy_id": "2"},
        ]
    )
    scraper.parse_vacancy_page = AsyncMock(return_value=page_data or _make_page_data())
    return scraper


class TestExtractorCompatFilter:
    @pytest.mark.asyncio
    async def test_vacancy_failing_compat_is_excluded_from_results(self):
        """A vacancy rejected by batch compat (score below threshold) must not appear."""
        from src.services.parser.extractor import ParsingExtractor

        ai_client = MagicMock()
        ai_client.calculate_compatibility_batch = AsyncMock(
            return_value={"1": 80.0, "2": 30.0}
        )
        ai_client.extract_keywords = AsyncMock(return_value=["Python"])

        extractor = ParsingExtractor(scraper=_make_scraper(), ai_client=ai_client)
        result = await extractor.run_pipeline(
            "https://hh.ru/search", "", 2, compat_params=(["Python"], "exp", 50)
        )

        result_titles = [v.title for v in result.vacancies]
        assert "Backend Dev" in result_titles
        assert "Java Dev" not in result_titles

    @pytest.mark.asyncio
    async def test_keyword_extraction_skipped_for_filtered_vacancy(self):
        """extract_keywords must NOT be called for a vacancy that fails batch compat."""
        from src.services.parser.extractor import ParsingExtractor

        ai_client = MagicMock()
        ai_client.calculate_compatibility_batch = AsyncMock(
            return_value={"1": 80.0, "2": 30.0}
        )
        ai_client.extract_keywords = AsyncMock(return_value=["Python"])

        extractor = ParsingExtractor(scraper=_make_scraper(), ai_client=ai_client)
        await extractor.run_pipeline(
            "https://hh.ru/search", "", 2, compat_params=(["Python"], "exp", 50)
        )

        assert ai_client.extract_keywords.await_count == 1

    @pytest.mark.asyncio
    async def test_vacancy_passing_compat_is_included_with_keywords(self):
        """A vacancy that passes batch compat must be in results with its keywords."""
        from src.services.parser.extractor import ParsingExtractor

        ai_client = MagicMock()
        ai_client.calculate_compatibility_batch = AsyncMock(
            return_value={"1": 80.0, "2": 75.0}
        )
        ai_client.extract_keywords = AsyncMock(return_value=["Python", "Docker"])

        extractor = ParsingExtractor(scraper=_make_scraper(), ai_client=ai_client)
        result = await extractor.run_pipeline(
            "https://hh.ru/search", "", 2, compat_params=(["Python"], "exp", 50)
        )

        assert len(result.vacancies) == 2
        assert dict(result.keywords).get("Python", 0) > 0

    @pytest.mark.asyncio
    async def test_progress_callback_called_for_filtered_vacancy(self):
        """on_vacancy_processed must fire even when a vacancy is skipped."""
        from src.services.parser.extractor import ParsingExtractor

        ai_client = MagicMock()
        ai_client.calculate_compatibility_batch = AsyncMock(
            return_value={"1": 20.0, "2": 10.0}
        )
        ai_client.extract_keywords = AsyncMock(return_value=[])

        processed_calls: list[tuple[int, int]] = []

        async def on_processed(current: int, total: int) -> None:
            processed_calls.append((current, total))

        extractor = ParsingExtractor(scraper=_make_scraper(), ai_client=ai_client)
        await extractor.run_pipeline(
            "https://hh.ru/search",
            "",
            2,
            compat_params=(["Python"], "exp", 50),
            on_vacancy_processed=on_processed,
        )

        assert len(processed_calls) == 2

    @pytest.mark.asyncio
    async def test_no_compat_filter_runs_full_pipeline(self):
        """Without a filter, all vacancies are processed normally."""
        from src.services.parser.extractor import ParsingExtractor

        ai_client = MagicMock()
        ai_client.extract_keywords = AsyncMock(return_value=["Go"])

        extractor = ParsingExtractor(scraper=_make_scraper(), ai_client=ai_client)
        result = await extractor.run_pipeline("https://hh.ru/search", "", 2)

        assert len(result.vacancies) == 2
        assert ai_client.extract_keywords.await_count == 2

    @pytest.mark.asyncio
    async def test_keywords_only_aggregated_from_passing_vacancies(self):
        """Keywords from rejected vacancies must not appear in the aggregated result."""
        from src.services.parser.extractor import ParsingExtractor

        ai_client = MagicMock()
        ai_client.calculate_compatibility_batch = AsyncMock(
            return_value={"1": 80.0, "2": 30.0}
        )
        ai_client.extract_keywords = AsyncMock(return_value=["SharedKw"])

        extractor = ParsingExtractor(scraper=_make_scraper(), ai_client=ai_client)
        result = await extractor.run_pipeline(
            "https://hh.ru/search", "", 2, compat_params=(["Python"], "exp", 50)
        )

        assert dict(result.keywords).get("SharedKw", 0) == 1


# ---------------------------------------------------------------------------
# _run_parsing_company_async: compat_params forwarded to run_pipeline
# ---------------------------------------------------------------------------


class TestParsingTaskCompatIntegration:
    @pytest.mark.asyncio
    async def test_compat_params_passed_to_run_pipeline_when_enabled(self):
        """When use_compatibility_check=True, compat_params must reach run_pipeline."""
        from src.schemas.vacancy import PipelineResult

        company = MagicMock()
        company.vacancy_title = "Backend"
        company.search_url = "https://hh.ru/search/vacancy?text=backend"
        company.keyword_filter = ""
        company.target_count = 5
        company.status = "pending"
        company.use_compatibility_check = True
        company.compatibility_threshold = 70

        pipeline_result = PipelineResult(vacancies=[], keywords=[], skills=[])
        captured_kwargs: list[dict] = []

        async def fake_run_pipeline(_self, *_args, **kwargs):
            captured_kwargs.append(kwargs)
            return pipeline_result

        settings_repo = AsyncMock()
        settings_repo.get_value = AsyncMock(return_value=True)
        company_repo = AsyncMock()
        company_repo.get_by_id = AsyncMock(return_value=company)
        company_repo.update = AsyncMock()
        task_repo = AsyncMock()
        task_repo.get_by_idempotency_key = AsyncMock(return_value=None)
        bl_repo = AsyncMock()
        bl_repo.get_active_ids = AsyncMock(return_value=set())

        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        session.commit = AsyncMock()
        session_factory = MagicMock(return_value=session)
        fake_task = MagicMock()
        fake_task.request.id = "test-id"

        mock_checkpoint = AsyncMock()
        mock_checkpoint.load_parsing = AsyncMock(return_value=None)
        mock_checkpoint.save_parsing = AsyncMock()
        mock_checkpoint.clear = AsyncMock()
        mock_scraper = AsyncMock()
        mock_scraper.collect_vacancy_urls = AsyncMock(
            return_value=[{"url": "https://hh.ru/vacancy/1", "title": "Test", "hh_vacancy_id": "1"}]
        )

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
            patch("src.repositories.app_settings.AppSettingRepository", return_value=settings_repo),
            patch("src.repositories.blacklist.BlacklistRepository", return_value=bl_repo),
            patch("src.repositories.parsing.ParsingCompanyRepository", return_value=company_repo),
            patch("src.repositories.task.CeleryTaskRepository", return_value=task_repo),
            patch(
                "src.worker.tasks.parsing._fetch_user_tech_profile",
                new=AsyncMock(return_value=(["Python"], "Company: Python")),
            ),
            patch(
                "src.services.parser.extractor.ParsingExtractor.run_pipeline", new=fake_run_pipeline
            ),
            patch(
                "src.services.task_checkpoint.TaskCheckpointService",
                return_value=mock_checkpoint,
            ),
            patch(
                "src.services.task_checkpoint.create_checkpoint_redis",
                return_value=MagicMock(),
            ),
            patch(
                "src.services.parser.scraper.HHScraper",
                return_value=mock_scraper,
            ),
        ):
            from src.worker.tasks.parsing import _run_parsing_company_async

            await _run_parsing_company_async(
                session_factory,
                fake_task,
                parsing_company_id=1,
                user_id=42,
                include_blacklisted=False,
                telegram_chat_id=0,
            )

        assert len(captured_kwargs) == 1
        assert captured_kwargs[0].get("compat_params") is not None, (
            "compat_params must be forwarded to run_pipeline"
        )
        params = captured_kwargs[0]["compat_params"]
        assert params == (["Python"], "Company: Python", 70)

    @pytest.mark.asyncio
    async def test_compat_params_is_none_when_disabled(self):
        """When use_compatibility_check=False, compat_params=None must be passed."""
        from src.schemas.vacancy import PipelineResult

        company = MagicMock()
        company.vacancy_title = "Backend"
        company.search_url = "https://hh.ru/search/vacancy?text=backend"
        company.keyword_filter = ""
        company.target_count = 5
        company.status = "pending"
        company.use_compatibility_check = False
        company.compatibility_threshold = None

        pipeline_result = PipelineResult(vacancies=[], keywords=[], skills=[])
        captured_kwargs: list[dict] = []

        async def fake_run_pipeline(_self, *_args, **kwargs):
            captured_kwargs.append(kwargs)
            return pipeline_result

        settings_repo = AsyncMock()
        settings_repo.get_value = AsyncMock(return_value=True)
        company_repo = AsyncMock()
        company_repo.get_by_id = AsyncMock(return_value=company)
        company_repo.update = AsyncMock()
        task_repo = AsyncMock()
        task_repo.get_by_idempotency_key = AsyncMock(return_value=None)
        bl_repo = AsyncMock()
        bl_repo.get_active_ids = AsyncMock(return_value=set())

        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        session.commit = AsyncMock()
        session_factory = MagicMock(return_value=session)
        fake_task = MagicMock()
        fake_task.request.id = "test-id"

        mock_checkpoint = AsyncMock()
        mock_checkpoint.load_parsing = AsyncMock(return_value=None)
        mock_checkpoint.save_parsing = AsyncMock()
        mock_checkpoint.clear = AsyncMock()
        mock_scraper = AsyncMock()
        mock_scraper.collect_vacancy_urls = AsyncMock(
            return_value=[{"url": "https://hh.ru/vacancy/1", "title": "Test", "hh_vacancy_id": "1"}]
        )

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
            patch("src.repositories.app_settings.AppSettingRepository", return_value=settings_repo),
            patch("src.repositories.blacklist.BlacklistRepository", return_value=bl_repo),
            patch("src.repositories.parsing.ParsingCompanyRepository", return_value=company_repo),
            patch("src.repositories.task.CeleryTaskRepository", return_value=task_repo),
            patch(
                "src.services.parser.extractor.ParsingExtractor.run_pipeline", new=fake_run_pipeline
            ),
            patch(
                "src.services.task_checkpoint.TaskCheckpointService",
                return_value=mock_checkpoint,
            ),
            patch(
                "src.services.task_checkpoint.create_checkpoint_redis",
                return_value=MagicMock(),
            ),
            patch(
                "src.services.parser.scraper.HHScraper",
                return_value=mock_scraper,
            ),
        ):
            from src.worker.tasks.parsing import _run_parsing_company_async

            await _run_parsing_company_async(
                session_factory,
                fake_task,
                parsing_company_id=1,
                user_id=42,
                include_blacklisted=False,
                telegram_chat_id=0,
            )

        assert captured_kwargs[0].get("compat_params") is None


# ---------------------------------------------------------------------------
# clone_and_dispatch: compat fields forwarded from source
# ---------------------------------------------------------------------------


class TestCloneAndDispatch:
    @pytest.mark.asyncio
    async def test_clone_forwards_compatibility_settings(self):
        """clone_and_dispatch must copy use_compatibility_check and threshold."""
        from src.bot.modules.parsing.services import clone_and_dispatch

        source = MagicMock()
        source.id = 1
        source.vacancy_title = "Backend Dev"
        source.search_url = "https://hh.ru/search/vacancy?text=backend"
        source.keyword_filter = "python"
        source.target_count = 20
        source.use_compatibility_check = True
        source.compatibility_threshold = 75

        repo = AsyncMock()
        repo.get_by_id = AsyncMock(return_value=source)
        session = AsyncMock()
        created_kwargs: list[dict] = []

        async def capture_create(**kwargs):
            created_kwargs.append(kwargs)
            return 99

        with (
            patch("src.bot.modules.parsing.services.ParsingCompanyRepository", return_value=repo),
            patch(
                "src.bot.modules.parsing.services.create_parsing_company",
                side_effect=capture_create,
            ),
            patch("src.bot.modules.parsing.services.dispatch_parsing_task"),
        ):
            await clone_and_dispatch(session, source_company_id=1, user_id=42)

        kwargs = created_kwargs[0]
        assert kwargs["use_compatibility_check"] is True
        assert kwargs["compatibility_threshold"] == 75

    @pytest.mark.asyncio
    async def test_clone_forwards_disabled_compatibility(self):
        """When source has compat disabled, clone must also have it disabled."""
        from src.bot.modules.parsing.services import clone_and_dispatch

        source = MagicMock()
        source.id = 2
        source.vacancy_title = "Frontend Dev"
        source.search_url = "https://hh.ru/search/vacancy?text=frontend"
        source.keyword_filter = ""
        source.target_count = 10
        source.use_compatibility_check = False
        source.compatibility_threshold = None

        repo = AsyncMock()
        repo.get_by_id = AsyncMock(return_value=source)
        session = AsyncMock()
        created_kwargs: list[dict] = []

        async def capture_create(**kwargs):
            created_kwargs.append(kwargs)
            return 100

        with (
            patch("src.bot.modules.parsing.services.ParsingCompanyRepository", return_value=repo),
            patch(
                "src.bot.modules.parsing.services.create_parsing_company",
                side_effect=capture_create,
            ),
            patch("src.bot.modules.parsing.services.dispatch_parsing_task"),
        ):
            await clone_and_dispatch(session, source_company_id=2, user_id=42)

        kwargs = created_kwargs[0]
        assert kwargs["use_compatibility_check"] is False
        assert kwargs["compatibility_threshold"] is None
