from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.ai.client import AIClient


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
