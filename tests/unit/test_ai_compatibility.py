from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.ai.client import (
    AIClient,
    _parse_batch_compat_response,
    _parse_batch_keywords_response,
)
from src.services.ai.prompts import (
    VacancyCompatInput,
    build_compatibility_system_prompt,
    build_compatibility_user_content,
)


class TestCalculateCompatibility:
    @pytest.mark.asyncio
    async def test_returns_score(self):
        client = AIClient(api_key="test", base_url="http://fake", model="test")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "75"

        with patch.object(
            client._client.chat.completions, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_response
            score = await client.calculate_compatibility(
                vacancy_title="Python Developer",
                vacancy_skills=["Python", "Django", "PostgreSQL"],
                vacancy_description="Looking for a Python dev",
                user_tech_stack=["Python", "FastAPI"],
                user_work_experience="3 years backend dev",
            )

        assert score == 75.0
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_caps_at_100(self):
        client = AIClient(api_key="test", base_url="http://fake", model="test")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "150"

        with patch.object(
            client._client.chat.completions, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_response
            score = await client.calculate_compatibility(
                vacancy_title="Dev",
                vacancy_skills=["Python"],
                vacancy_description="desc",
                user_tech_stack=["Python"],
                user_work_experience="exp",
            )

        assert score == 100.0

    @pytest.mark.asyncio
    async def test_returns_zero_on_error(self):
        client = AIClient(api_key="test", base_url="http://fake", model="test")

        with patch.object(
            client._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=Exception("API error"),
        ):
            score = await client.calculate_compatibility(
                vacancy_title="Dev",
                vacancy_skills=["Python"],
                vacancy_description="desc",
                user_tech_stack=["Java"],
                user_work_experience="exp",
            )

        assert score == 0.0

    @pytest.mark.asyncio
    async def test_handles_non_numeric_response(self):
        client = AIClient(api_key="test", base_url="http://fake", model="test")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Score: 82%"

        with patch.object(
            client._client.chat.completions, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_response
            score = await client.calculate_compatibility(
                vacancy_title="Dev",
                vacancy_skills=["Python"],
                vacancy_description="desc",
                user_tech_stack=["Python"],
                user_work_experience="exp",
            )

        assert score == 82.0

    @pytest.mark.asyncio
    async def test_uses_system_prompt_from_prompts_module(self):
        client = AIClient(api_key="test", base_url="http://fake", model="test")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "60"

        with (
            patch(
                "src.services.ai.client.build_compatibility_system_prompt",
                return_value="SENTINEL_PROMPT",
            ) as mock_prompt,
            patch.object(
                client._client.chat.completions, "create", new_callable=AsyncMock
            ) as mock_create,
        ):
            mock_create.return_value = mock_response
            await client.calculate_compatibility(
                vacancy_title="Dev",
                vacancy_skills=["Python"],
                vacancy_description="desc",
                user_tech_stack=["Python"],
                user_work_experience="exp",
            )

        mock_prompt.assert_called_once()
        sent_messages = mock_create.call_args.kwargs["messages"]
        assert sent_messages[0]["role"] == "system"
        assert sent_messages[0]["content"] == "SENTINEL_PROMPT"


class TestCompatibilityPrompt:
    def test_system_prompt_contains_expert_role(self):
        prompt = build_compatibility_system_prompt()
        assert "30" in prompt
        assert "Senior" in prompt

    def test_system_prompt_contains_output_rule(self):
        prompt = build_compatibility_system_prompt()
        assert "ТОЛЬКО" in prompt
        assert "0" in prompt
        assert "100" in prompt

    def test_system_prompt_contains_scale(self):
        prompt = build_compatibility_system_prompt()
        assert "0–20" in prompt
        assert "81–100" in prompt

    def test_system_prompt_includes_role_first_scoring_rule(self):
        prompt = build_compatibility_system_prompt()
        assert "как правило не выше 40" in prompt
        assert "ITSM, BPMN" in prompt

    def test_user_content_includes_all_fields(self):
        content = build_compatibility_user_content(
            vacancy_title="Python Dev",
            vacancy_skills=["Python", "Django"],
            vacancy_description="Build APIs",
            user_tech_stack=["Python", "FastAPI"],
            user_work_experience="3 years backend",
        )
        assert "Python Dev" in content
        assert "Python, Django" in content
        assert "Build APIs" in content
        assert "Python, FastAPI" in content
        assert "3 years backend" in content

    def test_user_content_truncates_long_description(self):
        long_desc = "x" * 5000
        content = build_compatibility_user_content(
            vacancy_title="Dev",
            vacancy_skills=[],
            vacancy_description=long_desc,
            user_tech_stack=[],
            user_work_experience="",
        )
        assert "x" * 4000 in content
        assert "x" * 4001 not in content


class TestParseBatchCompatResponse:
    def test_parses_valid_response(self):
        raw = (
            "[Vacancy]:v1\n[Compatibility]:72\n[VacancyEnd]:v1\n"
            "[Vacancy]:v2\n[Compatibility]:45\n[VacancyEnd]:v2\n"
        )
        result = _parse_batch_compat_response(raw)
        assert result == {"v1": 72.0, "v2": 45.0}

    def test_parses_without_vacancy_end(self):
        raw = "[Vacancy]:a1\n[Compatibility]:90\n[Vacancy]:b2\n[Compatibility]:33\n"
        result = _parse_batch_compat_response(raw)
        assert result == {"a1": 90.0, "b2": 33.0}

    def test_caps_score_at_100(self):
        raw = "[Vacancy]:x\n[Compatibility]:150\n"
        result = _parse_batch_compat_response(raw)
        assert result == {"x": 100.0}

    def test_returns_empty_for_empty_input(self):
        assert _parse_batch_compat_response("") == {}
        assert _parse_batch_compat_response("no valid blocks") == {}

    def test_handles_malformed_score(self):
        raw = "[Vacancy]:y\n[Compatibility]:abc\n"
        result = _parse_batch_compat_response(raw)
        assert result == {}


class TestParseBatchKeywordsResponse:
    def test_parse_batch_keywords_valid_response(self):
        raw = "[Vacancy]:a\n[Keywords]:Python, Django\n[VacancyEnd]:a"
        result = _parse_batch_keywords_response(raw)
        assert result == {"a": ["Python", "Django"]}

    def test_parse_batch_keywords_multiple_vacancies(self):
        raw = (
            "[Vacancy]:v1\n[Keywords]:Python, FastAPI\n[VacancyEnd]:v1\n"
            "[Vacancy]:v2\n[Keywords]:Java, Spring\n[VacancyEnd]:v2\n"
        )
        result = _parse_batch_keywords_response(raw)
        assert result == {"v1": ["Python", "FastAPI"], "v2": ["Java", "Spring"]}

    def test_parse_batch_keywords_returns_empty_for_malformed(self):
        result = _parse_batch_keywords_response("garbage input without markers")
        assert result == {}

    def test_parse_batch_keywords_handles_empty_keywords(self):
        raw = "[Vacancy]:x\n[Keywords]:\n[VacancyEnd]:x"
        result = _parse_batch_keywords_response(raw)
        assert result == {"x": []}


class TestCalculateCompatibilityBatch:
    @pytest.mark.asyncio
    async def test_returns_scores_for_batch(self):
        client = AIClient(api_key="test", base_url="http://fake", model="test")
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            "[Vacancy]:v1\n[Compatibility]:80\n[Vacancy]:v2\n[Compatibility]:55\n"
        )

        vacancies = [
            VacancyCompatInput("v1", "Dev 1", ["Python"], "desc1"),
            VacancyCompatInput("v2", "Dev 2", ["Java"], "desc2"),
        ]

        with patch.object(
            client._client.chat.completions, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_response
            scores = await client.calculate_compatibility_batch(
                vacancies,
                user_tech_stack=["Python"],
                user_work_experience="3 years",
            )

        assert scores == {"v1": 80.0, "v2": 55.0}
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_empty_for_empty_vacancies(self):
        client = AIClient(api_key="test", base_url="http://fake", model="test")
        scores = await client.calculate_compatibility_batch(
            [], user_tech_stack=[], user_work_experience=""
        )
        assert scores == {}

    @pytest.mark.asyncio
    async def test_returns_zeros_on_error(self):
        client = AIClient(api_key="test", base_url="http://fake", model="test")
        vacancies = [VacancyCompatInput("v1", "Dev", [], "desc")]

        with patch.object(
            client._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=Exception("API error"),
        ):
            scores = await client.calculate_compatibility_batch(
                vacancies, user_tech_stack=[], user_work_experience=""
            )

        assert scores == {"v1": 0.0}


class TestExtractKeywordsBatch:
    @pytest.mark.asyncio
    async def test_extract_keywords_batch_returns_keywords_for_batch(self):
        client = AIClient(api_key="test", base_url="http://fake", model="test")
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            "[Vacancy]:v1\n[Keywords]:Python, Django\n[VacancyEnd]:v1\n"
            "[Vacancy]:v2\n[Keywords]:Java, Spring\n[VacancyEnd]:v2\n"
        )

        vacancies = [
            VacancyCompatInput("v1", "Python Dev", ["Python"], "desc1"),
            VacancyCompatInput("v2", "Java Dev", ["Java"], "desc2"),
        ]

        with patch.object(
            client._client.chat.completions, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_response
            result = await client.extract_keywords_batch(vacancies)

        assert result == {"v1": ["Python", "Django"], "v2": ["Java", "Spring"]}
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_keywords_batch_fallback_on_error(self):
        client = AIClient(api_key="test", base_url="http://fake", model="test")
        vacancies = [
            VacancyCompatInput("v1", "Dev", [], "desc1"),
            VacancyCompatInput("v2", "Dev", [], "desc2"),
        ]

        with patch.object(
            client._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=Exception("API error"),
        ):
            result = await client.extract_keywords_batch(vacancies)

        assert result == {"v1": [], "v2": []}

    @pytest.mark.asyncio
    async def test_extract_keywords_batch_empty_input_returns_empty_dict(self):
        client = AIClient(api_key="test", base_url="http://fake", model="test")
        result = await client.extract_keywords_batch([])
        assert result == {}
