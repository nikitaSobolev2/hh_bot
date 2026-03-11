"""Tests for the inline compatibility filter: predicate factory and extractor integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# _build_compat_predicate
# ---------------------------------------------------------------------------


class TestCompatPredicate:
    @pytest.mark.asyncio
    async def test_returns_true_when_score_meets_threshold(self):
        from src.worker.tasks.parsing import _build_compat_predicate

        mock_client = AsyncMock()
        mock_client.calculate_compatibility = AsyncMock(return_value=75.0)

        with patch("src.services.ai.client.AIClient", return_value=mock_client):
            predicate = _build_compat_predicate(["Python"], "Company: Python", 70)
            result = await predicate({"title": "Dev", "raw_skills": [], "description": ""})

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_when_score_exactly_equals_threshold(self):
        from src.worker.tasks.parsing import _build_compat_predicate

        mock_client = AsyncMock()
        mock_client.calculate_compatibility = AsyncMock(return_value=70.0)

        with patch("src.services.ai.client.AIClient", return_value=mock_client):
            predicate = _build_compat_predicate(["Python"], "Company: Python", 70)
            result = await predicate({"title": "Dev", "raw_skills": [], "description": ""})

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_score_below_threshold(self):
        from src.worker.tasks.parsing import _build_compat_predicate

        mock_client = AsyncMock()
        mock_client.calculate_compatibility = AsyncMock(return_value=50.0)

        with patch("src.services.ai.client.AIClient", return_value=mock_client):
            predicate = _build_compat_predicate(["Python"], "Company: Python", 70)
            result = await predicate({"title": "Dev", "raw_skills": [], "description": ""})

        assert result is False

    @pytest.mark.asyncio
    async def test_passes_correct_args_to_calculate_compatibility(self):
        from src.worker.tasks.parsing import _build_compat_predicate

        mock_client = AsyncMock()
        mock_client.calculate_compatibility = AsyncMock(return_value=80.0)

        vacancy = {
            "title": "Backend Dev",
            "raw_skills": ["Python", "Docker"],
            "description": "We need a backend engineer",
        }

        with patch("src.services.ai.client.AIClient", return_value=mock_client):
            predicate = _build_compat_predicate(
                ["Python", "FastAPI"], "Company: Python, FastAPI", 60
            )
            await predicate(vacancy)

        mock_client.calculate_compatibility.assert_awaited_once_with(
            vacancy_title="Backend Dev",
            vacancy_skills=["Python", "Docker"],
            vacancy_description="We need a backend engineer",
            user_tech_stack=["Python", "FastAPI"],
            user_work_experience="Company: Python, FastAPI",
        )

    @pytest.mark.asyncio
    async def test_reuses_single_ai_client_across_calls(self):
        """The factory must create one AIClient, not one per call."""
        from src.worker.tasks.parsing import _build_compat_predicate

        mock_client = AsyncMock()
        mock_client.calculate_compatibility = AsyncMock(return_value=90.0)
        constructor_calls = []

        def tracking_constructor(*args, **kwargs):
            constructor_calls.append(1)
            return mock_client

        with patch("src.services.ai.client.AIClient", side_effect=tracking_constructor):
            predicate = _build_compat_predicate([], "", 50)
            await predicate({"title": "A", "raw_skills": [], "description": ""})
            await predicate({"title": "B", "raw_skills": [], "description": ""})

        assert len(constructor_calls) == 1, "AIClient must be instantiated once per predicate"


# ---------------------------------------------------------------------------
# ParsingExtractor.run_pipeline with compat_filter
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
        """A vacancy rejected by the filter must not appear in result['vacancies']."""
        from src.services.parser.extractor import ParsingExtractor

        titles_seen: list[str] = []

        async def reject_java(vac: dict) -> bool:
            titles_seen.append(vac["title"])
            return vac["title"] != "Java Dev"

        ai_client = MagicMock()
        ai_client.extract_keywords = AsyncMock(return_value=["Python"])

        extractor = ParsingExtractor(scraper=_make_scraper(), ai_client=ai_client)
        result = await extractor.run_pipeline(
            "https://hh.ru/search", "", 2, compat_filter=reject_java
        )

        result_titles = [v["title"] for v in result["vacancies"]]
        assert "Backend Dev" in result_titles
        assert "Java Dev" not in result_titles

    @pytest.mark.asyncio
    async def test_keyword_extraction_skipped_for_filtered_vacancy(self):
        """extract_keywords must NOT be called for a vacancy that fails the filter."""
        from src.services.parser.extractor import ParsingExtractor

        async def reject_java(vac: dict) -> bool:
            return vac["title"] != "Java Dev"

        ai_client = MagicMock()
        ai_client.extract_keywords = AsyncMock(return_value=["Python"])

        extractor = ParsingExtractor(scraper=_make_scraper(), ai_client=ai_client)
        await extractor.run_pipeline("https://hh.ru/search", "", 2, compat_filter=reject_java)

        # Only one call: for "Backend Dev". "Java Dev" must not trigger extraction.
        assert ai_client.extract_keywords.await_count == 1

    @pytest.mark.asyncio
    async def test_vacancy_passing_compat_is_included_with_keywords(self):
        """A vacancy that passes the filter must be in results with its keywords."""
        from src.services.parser.extractor import ParsingExtractor

        async def accept_all(vac: dict) -> bool:
            return True

        ai_client = MagicMock()
        ai_client.extract_keywords = AsyncMock(return_value=["Python", "Docker"])

        extractor = ParsingExtractor(scraper=_make_scraper(), ai_client=ai_client)
        result = await extractor.run_pipeline(
            "https://hh.ru/search", "", 2, compat_filter=accept_all
        )

        assert len(result["vacancies"]) == 2
        assert result["keywords"].get("Python", 0) > 0

    @pytest.mark.asyncio
    async def test_progress_callback_called_for_filtered_vacancy(self):
        """on_vacancy_processed must fire even when a vacancy is skipped."""
        from src.services.parser.extractor import ParsingExtractor

        async def reject_all(_vac: dict) -> bool:
            return False

        ai_client = MagicMock()
        ai_client.extract_keywords = AsyncMock(return_value=[])

        processed_calls: list[tuple[int, int]] = []

        async def on_processed(current: int, total: int) -> None:
            processed_calls.append((current, total))

        extractor = ParsingExtractor(scraper=_make_scraper(), ai_client=ai_client)
        await extractor.run_pipeline(
            "https://hh.ru/search",
            "",
            2,
            compat_filter=reject_all,
            on_vacancy_processed=on_processed,
        )

        assert len(processed_calls) == 2, "callback must fire for every vacancy including skipped"

    @pytest.mark.asyncio
    async def test_no_compat_filter_runs_full_pipeline(self):
        """Without a filter, all vacancies are processed normally."""
        from src.services.parser.extractor import ParsingExtractor

        ai_client = MagicMock()
        ai_client.extract_keywords = AsyncMock(return_value=["Go"])

        extractor = ParsingExtractor(scraper=_make_scraper(), ai_client=ai_client)
        result = await extractor.run_pipeline("https://hh.ru/search", "", 2)

        assert len(result["vacancies"]) == 2
        assert ai_client.extract_keywords.await_count == 2

    @pytest.mark.asyncio
    async def test_keywords_only_aggregated_from_passing_vacancies(self):
        """Keywords from rejected vacancies must not appear in the aggregated result."""
        from src.services.parser.extractor import ParsingExtractor

        # Java Dev gets rejected; its keywords must not appear.
        async def reject_java(vac: dict) -> bool:
            return vac["title"] != "Java Dev"

        async def fake_keywords(description: str) -> list[str]:
            # Both vacancies have the same description in the mock, so we
            # use a simple call-count trick instead.
            return ["SharedKw"]

        ai_client = MagicMock()
        ai_client.extract_keywords = AsyncMock(side_effect=fake_keywords)

        extractor = ParsingExtractor(scraper=_make_scraper(), ai_client=ai_client)
        result = await extractor.run_pipeline(
            "https://hh.ru/search", "", 2, compat_filter=reject_java
        )

        # Only 1 vacancy passed → keyword count must be 1, not 2.
        assert result["keywords"].get("SharedKw", 0) == 1


# ---------------------------------------------------------------------------
# _run_parsing_company_async: compat_filter forwarded to run_pipeline
# ---------------------------------------------------------------------------


class TestParsingTaskCompatIntegration:
    @pytest.mark.asyncio
    async def test_compat_filter_passed_to_run_pipeline_when_enabled(self):
        """When use_compatibility_check=True, a compat_filter must reach run_pipeline."""
        company = MagicMock()
        company.vacancy_title = "Backend"
        company.search_url = "https://hh.ru/search/vacancy?text=backend"
        company.keyword_filter = ""
        company.target_count = 5
        company.status = "pending"
        company.use_compatibility_check = True
        company.compatibility_threshold = 70

        pipeline_result = {"vacancies": [], "keywords": {}, "skills": {}}
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
            patch("src.repositories.app_settings.AppSettingRepository", return_value=settings_repo),
            patch("src.repositories.blacklist.BlacklistRepository", return_value=bl_repo),
            patch("src.repositories.parsing.ParsingCompanyRepository", return_value=company_repo),
            patch("src.repositories.task.CeleryTaskRepository", return_value=task_repo),
            patch(
                "src.worker.tasks.parsing._fetch_user_tech_profile",
                new=AsyncMock(return_value=(["Python"], "Company: Python")),
            ),
            patch(
                "src.worker.tasks.parsing._build_compat_predicate",
                return_value=AsyncMock(return_value=True),
            ),
            patch(
                "src.services.parser.extractor.ParsingExtractor.run_pipeline", new=fake_run_pipeline
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
        assert captured_kwargs[0].get("compat_filter") is not None, (
            "compat_filter must be forwarded to run_pipeline"
        )

    @pytest.mark.asyncio
    async def test_compat_filter_is_none_when_disabled(self):
        """When use_compatibility_check=False, compat_filter=None must be passed."""
        company = MagicMock()
        company.vacancy_title = "Backend"
        company.search_url = "https://hh.ru/search/vacancy?text=backend"
        company.keyword_filter = ""
        company.target_count = 5
        company.status = "pending"
        company.use_compatibility_check = False
        company.compatibility_threshold = None

        pipeline_result = {"vacancies": [], "keywords": {}, "skills": {}}
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

        build_mock = MagicMock()

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
            patch("src.repositories.app_settings.AppSettingRepository", return_value=settings_repo),
            patch("src.repositories.blacklist.BlacklistRepository", return_value=bl_repo),
            patch("src.repositories.parsing.ParsingCompanyRepository", return_value=company_repo),
            patch("src.repositories.task.CeleryTaskRepository", return_value=task_repo),
            patch("src.worker.tasks.parsing._build_compat_predicate", new=build_mock),
            patch(
                "src.services.parser.extractor.ParsingExtractor.run_pipeline", new=fake_run_pipeline
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

        build_mock.assert_not_called()
        assert captured_kwargs[0].get("compat_filter") is None


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
