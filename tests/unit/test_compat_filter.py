"""Tests for the compatibility filter helpers in the manual parsing task."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# _recompute_aggregates
# ---------------------------------------------------------------------------


class TestRecomputeAggregates:
    def test_sums_keywords_from_all_vacancies(self):
        from src.worker.tasks.parsing import _recompute_aggregates

        vacancies = [
            {"ai_keywords": ["Python", "Docker"], "raw_skills": ["SQL"]},
            {"ai_keywords": ["Python", "FastAPI"], "raw_skills": ["SQL", "Redis"]},
        ]
        keywords, skills = _recompute_aggregates(vacancies)

        assert keywords["Python"] == 2
        assert keywords["Docker"] == 1
        assert keywords["FastAPI"] == 1

    def test_sums_skills_from_all_vacancies(self):
        from src.worker.tasks.parsing import _recompute_aggregates

        vacancies = [
            {"ai_keywords": [], "raw_skills": ["SQL", "Redis"]},
            {"ai_keywords": [], "raw_skills": ["SQL"]},
        ]
        _, skills = _recompute_aggregates(vacancies)

        assert skills["SQL"] == 2
        assert skills["Redis"] == 1

    def test_returns_empty_dicts_for_empty_vacancy_list(self):
        from src.worker.tasks.parsing import _recompute_aggregates

        keywords, skills = _recompute_aggregates([])

        assert keywords == {}
        assert skills == {}

    def test_handles_vacancies_with_none_fields_gracefully(self):
        from src.worker.tasks.parsing import _recompute_aggregates

        vacancies = [
            {"ai_keywords": None, "raw_skills": None},
            {"ai_keywords": ["Go"], "raw_skills": []},
        ]
        keywords, skills = _recompute_aggregates(vacancies)

        assert keywords == {"Go": 1}
        assert skills == {}

    def test_strips_whitespace_from_keywords(self):
        from src.worker.tasks.parsing import _recompute_aggregates

        vacancies = [{"ai_keywords": [" Python ", "Docker"], "raw_skills": [" SQL "]}]
        keywords, skills = _recompute_aggregates(vacancies)

        assert "Python" in keywords
        assert "SQL" in skills


# ---------------------------------------------------------------------------
# _apply_compatibility_filter
# ---------------------------------------------------------------------------


class TestApplyCompatibilityFilter:
    @pytest.mark.asyncio
    async def test_keeps_vacancy_above_threshold(self):
        from src.worker.tasks.parsing import _apply_compatibility_filter

        vacancies = [{"title": "Backend Dev", "raw_skills": [], "description": "..."}]
        mock_client = AsyncMock()
        mock_client.calculate_compatibility = AsyncMock(return_value=80.0)

        with patch("src.services.ai.client.AIClient", return_value=mock_client):
            result = await _apply_compatibility_filter(vacancies, 70, ["Python"], "exp")

        assert len(result) == 1
        assert result[0]["title"] == "Backend Dev"

    @pytest.mark.asyncio
    async def test_discards_vacancy_below_threshold(self):
        from src.worker.tasks.parsing import _apply_compatibility_filter

        vacancies = [{"title": "Java Dev", "raw_skills": [], "description": "..."}]
        mock_client = AsyncMock()
        mock_client.calculate_compatibility = AsyncMock(return_value=40.0)

        with patch("src.services.ai.client.AIClient", return_value=mock_client):
            result = await _apply_compatibility_filter(vacancies, 70, ["Python"], "exp")

        assert result == []

    @pytest.mark.asyncio
    async def test_vacancy_exactly_at_threshold_is_kept(self):
        from src.worker.tasks.parsing import _apply_compatibility_filter

        vacancies = [{"title": "Dev", "raw_skills": [], "description": "..."}]
        mock_client = AsyncMock()
        mock_client.calculate_compatibility = AsyncMock(return_value=70.0)

        with patch("src.services.ai.client.AIClient", return_value=mock_client):
            result = await _apply_compatibility_filter(vacancies, 70, ["Python"], "exp")

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_returns_empty_when_all_vacancies_below_threshold(self):
        from src.worker.tasks.parsing import _apply_compatibility_filter

        vacancies = [
            {"title": "Java Dev", "raw_skills": [], "description": "..."},
            {"title": "PHP Dev", "raw_skills": [], "description": "..."},
        ]
        mock_client = AsyncMock()
        mock_client.calculate_compatibility = AsyncMock(return_value=10.0)

        with patch("src.services.ai.client.AIClient", return_value=mock_client):
            result = await _apply_compatibility_filter(vacancies, 70, [], "")

        assert result == []

    @pytest.mark.asyncio
    async def test_passes_correct_args_to_ai_client(self):
        from src.worker.tasks.parsing import _apply_compatibility_filter

        vacancy = {
            "title": "Backend Dev",
            "raw_skills": ["Python", "Docker"],
            "description": "We need a backend engineer",
        }
        mock_client = AsyncMock()
        mock_client.calculate_compatibility = AsyncMock(return_value=90.0)

        with patch("src.services.ai.client.AIClient", return_value=mock_client):
            await _apply_compatibility_filter(
                [vacancy], 50, ["Python", "FastAPI"], "Company: Python, FastAPI"
            )

        mock_client.calculate_compatibility.assert_awaited_once_with(
            vacancy_title="Backend Dev",
            vacancy_skills=["Python", "Docker"],
            vacancy_description="We need a backend engineer",
            user_tech_stack=["Python", "FastAPI"],
            user_work_experience="Company: Python, FastAPI",
        )

    @pytest.mark.asyncio
    async def test_filters_mixed_vacancies_correctly(self):
        from src.worker.tasks.parsing import _apply_compatibility_filter

        vacancies = [
            {"title": "Good Dev", "raw_skills": [], "description": ""},
            {"title": "Bad Dev", "raw_skills": [], "description": ""},
            {"title": "Ok Dev", "raw_skills": [], "description": ""},
        ]
        scores = [85.0, 30.0, 75.0]
        call_count = 0

        async def side_effect(**_kwargs):
            nonlocal call_count
            score = scores[call_count]
            call_count += 1
            return score

        mock_client = AsyncMock()
        mock_client.calculate_compatibility = AsyncMock(side_effect=side_effect)

        with patch("src.services.ai.client.AIClient", return_value=mock_client):
            result = await _apply_compatibility_filter(vacancies, 70, [], "")

        titles = [v["title"] for v in result]
        assert "Good Dev" in titles
        assert "Ok Dev" in titles
        assert "Bad Dev" not in titles


# ---------------------------------------------------------------------------
# _run_parsing_company_async: compat filter integration
# ---------------------------------------------------------------------------


class TestParsingTaskCompatIntegration:
    @pytest.mark.asyncio
    async def test_compat_filter_called_when_enabled(self):
        """When use_compatibility_check=True, _apply_compatibility_filter must be called."""
        from unittest.mock import patch

        company = MagicMock()
        company.vacancy_title = "Backend"
        company.search_url = "https://hh.ru/search/vacancy?text=backend"
        company.keyword_filter = ""
        company.target_count = 5
        company.status = "pending"
        company.use_compatibility_check = True
        company.compatibility_threshold = 70

        pipeline_vacancies = [
            {
                "title": "Good Dev",
                "raw_skills": [],
                "description": "",
                "hh_vacancy_id": "1",
                "url": "https://hh.ru/1",
                "ai_keywords": ["Python"],
            },
        ]
        pipeline_result = {"vacancies": pipeline_vacancies, "keywords": {"Python": 1}, "skills": {}}

        filter_called_with: list = []

        async def fake_filter(vacancies, threshold, tech_stack, work_exp_text):
            filter_called_with.extend([threshold, tech_stack])
            return vacancies

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
                "src.services.parser.extractor.ParsingExtractor.run_pipeline",
                new=AsyncMock(return_value=pipeline_result),
            ),
            patch(
                "src.worker.tasks.parsing._fetch_user_tech_profile",
                new=AsyncMock(return_value=(["Python"], "Company: Python")),
            ),
            patch(
                "src.worker.tasks.parsing._apply_compatibility_filter",
                new=AsyncMock(side_effect=fake_filter),
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

        assert 70 in filter_called_with, "filter must be called with threshold=70"

    @pytest.mark.asyncio
    async def test_compat_filter_skipped_when_disabled(self):
        """When use_compatibility_check=False, _apply_compatibility_filter must not be called."""
        company = MagicMock()
        company.vacancy_title = "Backend"
        company.search_url = "https://hh.ru/search/vacancy?text=backend"
        company.keyword_filter = ""
        company.target_count = 5
        company.status = "pending"
        company.use_compatibility_check = False
        company.compatibility_threshold = None

        pipeline_result = {"vacancies": [], "keywords": {}, "skills": {}}

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

        filter_mock = AsyncMock()

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
                "src.services.parser.extractor.ParsingExtractor.run_pipeline",
                new=AsyncMock(return_value=pipeline_result),
            ),
            patch("src.worker.tasks.parsing._apply_compatibility_filter", new=filter_mock),
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

        filter_mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# clone_and_dispatch: compat fields forwarded from source
# ---------------------------------------------------------------------------


class TestCloneAndDispatch:
    @pytest.mark.asyncio
    async def test_clone_forwards_compatibility_settings(self):
        """clone_and_dispatch must copy use_compatibility_check and threshold."""
        from unittest.mock import AsyncMock, MagicMock, patch

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
            patch(
                "src.bot.modules.parsing.services.ParsingCompanyRepository",
                return_value=repo,
            ),
            patch(
                "src.bot.modules.parsing.services.create_parsing_company",
                side_effect=capture_create,
            ),
            patch("src.bot.modules.parsing.services.dispatch_parsing_task"),
        ):
            await clone_and_dispatch(session, source_company_id=1, user_id=42)

        assert len(created_kwargs) == 1
        kwargs = created_kwargs[0]
        assert kwargs["use_compatibility_check"] is True
        assert kwargs["compatibility_threshold"] == 75

    @pytest.mark.asyncio
    async def test_clone_forwards_disabled_compatibility(self):
        """When source has compat disabled, clone must also have it disabled."""
        from unittest.mock import AsyncMock, MagicMock, patch

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
            patch(
                "src.bot.modules.parsing.services.ParsingCompanyRepository",
                return_value=repo,
            ),
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
