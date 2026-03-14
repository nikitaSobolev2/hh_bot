from unittest.mock import AsyncMock, MagicMock, patch

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


def _make_compat_scraper(urls: list[dict]):
    """Scraper mock for compat flow: first call returns urls, second returns empty."""
    scraper = MagicMock()
    scraper.collect_vacancy_urls_batch = AsyncMock(
        side_effect=[(urls, 1, False), ([], 1, False)]
    )
    scraper.parse_vacancy_page = AsyncMock(
        return_value={"description": "desc", "skills": ["Python"]}
    )
    return scraper


class TestExtractorBatchCompat:
    """Tests for batch compatibility scoring in the extractor."""

    @pytest.mark.asyncio
    async def test_calls_calculate_compatibility_batch_with_correct_batch_size(self):
        from src.services.parser.extractor import ParsingExtractor

        urls = [
            {"url": "https://hh.ru/1", "title": "V1", "hh_vacancy_id": "1"},
            {"url": "https://hh.ru/2", "title": "V2", "hh_vacancy_id": "2"},
        ]
        scraper = _make_compat_scraper(urls)
        scraper.parse_vacancy_page = AsyncMock(
            return_value={"description": "desc", "skills": ["Python"]}
        )

        ai_client = MagicMock()
        ai_client.calculate_compatibility_batch = AsyncMock(return_value={"1": 80.0, "2": 60.0})
        ai_client.extract_keywords = AsyncMock(return_value=["Python"])

        extractor = ParsingExtractor(scraper=scraper, ai_client=ai_client)
        await extractor.run_pipeline(
            "https://hh.ru/search",
            "",
            2,
            compat_params=(["Python"], "3 years", 50),
        )

        ai_client.calculate_compatibility_batch.assert_called_once()
        call_args = ai_client.calculate_compatibility_batch.call_args
        vacancies = call_args.args[0] if call_args.args else call_args.kwargs["vacancies"]
        assert len(vacancies) == 2
        assert vacancies[0].hh_vacancy_id == "1"
        assert vacancies[1].hh_vacancy_id == "2"
        assert call_args.kwargs.get("user_tech_stack") == ["Python"]
        assert call_args.kwargs.get("user_work_experience") == "3 years"

    @pytest.mark.asyncio
    async def test_filters_by_threshold(self):
        from src.services.parser.extractor import ParsingExtractor

        urls = [
            {"url": "https://hh.ru/1", "title": "V1", "hh_vacancy_id": "1"},
            {"url": "https://hh.ru/2", "title": "V2", "hh_vacancy_id": "2"},
        ]
        scraper = _make_compat_scraper(urls)
        scraper.parse_vacancy_page = AsyncMock(return_value={"description": "desc", "skills": []})

        ai_client = MagicMock()
        ai_client.calculate_compatibility_batch = AsyncMock(return_value={"1": 70.0, "2": 30.0})
        ai_client.extract_keywords = AsyncMock(return_value=["kw"])

        extractor = ParsingExtractor(scraper=scraper, ai_client=ai_client)
        result = await extractor.run_pipeline(
            "https://hh.ru/search", "", 2, compat_params=(["Python"], "exp", 50)
        )

        assert len(result.vacancies) == 1
        assert result.vacancies[0].hh_vacancy_id == "1"
