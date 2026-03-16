"""Unit tests for the AI key phrases generation Celery task."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_session_factory():
    session = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory, session


class TestKeyPhraseExtraction:
    """Tests for the shared keyword extraction prompt builders."""

    def test_keyword_extraction_system_prompt_contains_rules(self):
        from src.services.ai.prompts import build_keyword_extraction_system_prompt

        prompt = build_keyword_extraction_system_prompt()
        assert "ПРАВИЛА" in prompt
        assert "hard skills" in prompt

    def test_keyword_extraction_system_prompt_forbids_soft_skills(self):
        from src.services.ai.prompts import build_keyword_extraction_system_prompt

        prompt = build_keyword_extraction_system_prompt()
        assert "soft skills" in prompt.lower() or "НЕ извлекай" in prompt

    def test_keyword_extraction_user_content_includes_description(self):
        from src.services.ai.prompts import build_keyword_extraction_user_content

        description = "We need a Python engineer with Django experience."
        content = build_keyword_extraction_user_content(description)
        assert description in content

    def test_keyword_extraction_user_content_has_instruction_prefix(self):
        from src.services.ai.prompts import build_keyword_extraction_user_content

        content = build_keyword_extraction_user_content("some text")
        assert "Извлеки" in content


class TestAIClientKeywordExtraction:
    """Tests for AIClient.extract_keywords."""

    @pytest.mark.asyncio
    async def test_extract_keywords_returns_empty_list_for_empty_description(self):
        from src.services.ai.client import AIClient

        client = AIClient(api_key="fake", base_url="http://fake", model="gpt-test")
        result = await client.extract_keywords("")
        assert result == []

    @pytest.mark.asyncio
    async def test_extract_keywords_returns_empty_list_for_whitespace_description(self):
        from src.services.ai.client import AIClient

        client = AIClient(api_key="fake", base_url="http://fake", model="gpt-test")
        result = await client.extract_keywords("   ")
        assert result == []

    @pytest.mark.asyncio
    async def test_extract_keywords_returns_list_on_successful_response(self):
        from unittest.mock import AsyncMock

        from src.services.ai.client import AIClient

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Python, Django, PostgreSQL"

        client = AIClient(api_key="fake", base_url="http://fake", model="gpt-test")
        client._client = MagicMock()
        client._client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await client.extract_keywords("Python developer needed")
        assert result == ["Python", "Django", "PostgreSQL"]

    @pytest.mark.asyncio
    async def test_extract_keywords_returns_empty_list_on_api_error(self):
        from unittest.mock import AsyncMock

        from src.services.ai.client import AIClient

        client = AIClient(api_key="fake", base_url="http://fake", model="gpt-test")
        client._client = MagicMock()
        client._client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))

        result = await client.extract_keywords("Python developer needed")
        assert result == []

    @pytest.mark.asyncio
    async def test_extract_keywords_truncates_long_descriptions(self):
        """Verify descriptions longer than AI_MAX_DESCRIPTION_LENGTH are truncated."""
        from src.core.constants import AI_MAX_DESCRIPTION_LENGTH
        from src.services.ai.client import AIClient

        client = AIClient(api_key="fake", base_url="http://fake", model="gpt-test")
        client._client = MagicMock()

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Python"

        captured_calls = []

        async def capture_create(**kwargs):
            captured_calls.append(kwargs)
            return mock_response

        client._client.chat.completions.create = capture_create

        long_description = "x" * (AI_MAX_DESCRIPTION_LENGTH + 1000)
        await client.extract_keywords(long_description)

        assert len(captured_calls) == 1
        user_message = captured_calls[0]["messages"][-1]["content"]
        assert len(user_message) <= AI_MAX_DESCRIPTION_LENGTH + 100


class TestAIClientStreamText:
    """Tests for AIClient.stream_text."""

    @pytest.mark.asyncio
    async def test_stream_text_yields_chunks(self):
        from src.services.ai.client import AIClient

        async def mock_stream():
            chunk1 = MagicMock()
            chunk1.choices = [MagicMock()]
            chunk1.choices[0].delta = MagicMock()
            chunk1.choices[0].delta.content = "Hello "
            chunk2 = MagicMock()
            chunk2.choices = [MagicMock()]
            chunk2.choices[0].delta = MagicMock()
            chunk2.choices[0].delta.content = "world"
            chunk3 = MagicMock()
            chunk3.choices = [MagicMock()]
            chunk3.choices[0].delta = MagicMock()
            chunk3.choices[0].delta.content = None
            for c in (chunk1, chunk2, chunk3):
                yield c

        client = AIClient(api_key="fake", base_url="http://fake", model="gpt-test")
        client._acquire_rate_limit = AsyncMock()
        client._client = MagicMock()
        client._client.chat.completions.create = AsyncMock(
            side_effect=lambda **kw: mock_stream()
        )

        chunks = []
        async for chunk in client.stream_text("test", system_prompt="system"):
            chunks.append(chunk)

        assert chunks == ["Hello ", "world"]

    @pytest.mark.asyncio
    async def test_stream_text_includes_system_prompt_in_messages(self):
        from src.services.ai.client import AIClient

        async def mock_stream():
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content="x"))])

        client = AIClient(api_key="fake", base_url="http://fake", model="gpt-test")
        client._acquire_rate_limit = AsyncMock()
        client._client = MagicMock()
        client._client.chat.completions.create = AsyncMock(
            side_effect=lambda **kw: mock_stream()
        )

        async for _ in client.stream_text("user", system_prompt="system"):
            break

        call_args = client._client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "user"


class TestRateLimiter:
    """Tests for the Redis-backed rate limiter."""

    @pytest.mark.asyncio
    async def test_acquire_allows_first_request_within_limit(self):
        from unittest.mock import AsyncMock

        from src.worker.throttle import RateLimiter

        redis = AsyncMock()
        redis.incr = AsyncMock(return_value=1)
        redis.expire = AsyncMock()
        redis.decr = AsyncMock()

        limiter = RateLimiter(redis, namespace="test", max_requests=5, window_seconds=1)
        await limiter.acquire()

        redis.incr.assert_called_once()

    @pytest.mark.asyncio
    async def test_acquire_decrements_and_retries_when_over_limit(self):
        from unittest.mock import AsyncMock, patch

        from src.worker.throttle import RateLimiter

        redis = AsyncMock()
        call_count = 0

        async def mock_incr(key):
            nonlocal call_count
            call_count += 1
            return 6 if call_count == 1 else 1

        redis.incr = mock_incr
        redis.expire = AsyncMock()
        redis.decr = AsyncMock()

        limiter = RateLimiter(redis, namespace="test", max_requests=5, window_seconds=1)

        with patch("asyncio.sleep", AsyncMock()):
            await limiter.acquire()

        assert call_count == 2
