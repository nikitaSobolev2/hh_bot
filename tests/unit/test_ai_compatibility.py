from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.ai.client import AIClient
from src.services.ai.prompts import (
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
        assert "0-20" in prompt
        assert "76-100" in prompt

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
