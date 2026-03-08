from unittest.mock import AsyncMock, patch

import pytest

from src.services.ai.client import MAX_DESCRIPTION_LENGTH, AIClient


class TestExtractKeywords:
    @pytest.mark.asyncio
    async def test_extracts_keywords_from_response(self, mock_openai_response):
        client = AIClient(api_key="test-key")

        with patch.object(
            client._client.chat.completions, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_openai_response
            keywords = await client.extract_keywords("Some vacancy description")

        assert "Python" in keywords
        assert "Django" in keywords
        assert len(keywords) == 5

    @pytest.mark.asyncio
    async def test_returns_empty_for_blank_description(self):
        client = AIClient(api_key="test-key")
        keywords = await client.extract_keywords("")
        assert keywords == []

    @pytest.mark.asyncio
    async def test_returns_empty_for_whitespace_description(self):
        client = AIClient(api_key="test-key")
        keywords = await client.extract_keywords("   ")
        assert keywords == []

    @pytest.mark.asyncio
    async def test_handles_api_error_gracefully(self):
        client = AIClient(api_key="test-key")

        with patch.object(
            client._client.chat.completions, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_create.side_effect = Exception("API Error")
            keywords = await client.extract_keywords("Some description")

        assert keywords == []

    @pytest.mark.asyncio
    async def test_truncates_long_descriptions(self, mock_openai_response):
        client = AIClient(api_key="test-key")

        with patch.object(
            client._client.chat.completions, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_openai_response
            long_desc = "x" * (MAX_DESCRIPTION_LENGTH + 2000)
            await client.extract_keywords(long_desc)

            call_args = mock_create.call_args
            user_content = call_args.kwargs["messages"][1]["content"]
            assert len(user_content) < len(long_desc)
            assert len(user_content) <= MAX_DESCRIPTION_LENGTH + 200
