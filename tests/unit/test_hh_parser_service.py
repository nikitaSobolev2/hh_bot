from unittest.mock import AsyncMock, patch

import pytest

from src.services.parser.hh_parser_service import HHParserService


class TestHHParserServiceDedup:
    @pytest.mark.asyncio
    async def test_cached_vacancies_marked(self):
        service = HHParserService()

        collected = [
            {"url": "https://hh.ru/vacancy/1", "title": "Dev 1", "hh_vacancy_id": "1"},
            {"url": "https://hh.ru/vacancy/2", "title": "Dev 2", "hh_vacancy_id": "2"},
            {"url": "https://hh.ru/vacancy/3", "title": "Dev 3", "hh_vacancy_id": "3"},
        ]

        page_data = {
            "description": "test",
            "skills": ["Python"],
        }

        with (
            patch.object(
                service._scraper, "collect_vacancy_urls", new_callable=AsyncMock
            ) as mock_collect,
            patch.object(
                service._scraper, "parse_vacancy_page", new_callable=AsyncMock
            ) as mock_parse,
        ):
            mock_collect.return_value = collected
            mock_parse.return_value = page_data

            results = await service.parse_vacancies(
                "https://hh.ru/search", "python", 10, known_hh_ids={"1", "3"}
            )

        cached = [r for r in results if r.get("cached")]
        assert len(cached) == 2
        assert {r["hh_vacancy_id"] for r in cached} == {"1", "3"}

        new = [r for r in results if not r.get("cached")]
        assert len(new) == 1
        assert new[0]["hh_vacancy_id"] == "2"

    @pytest.mark.asyncio
    async def test_respects_target_count(self):
        service = HHParserService()

        collected = [
            {"url": f"https://hh.ru/vacancy/{i}", "title": f"Dev {i}", "hh_vacancy_id": str(i)}
            for i in range(10)
        ]

        with (
            patch.object(
                service._scraper, "collect_vacancy_urls", new_callable=AsyncMock
            ) as mock_collect,
            patch.object(
                service._scraper, "parse_vacancy_page", new_callable=AsyncMock
            ) as mock_parse,
        ):
            mock_collect.return_value = collected
            mock_parse.return_value = {"description": "d", "skills": []}

            results = await service.parse_vacancies(
                "https://hh.ru/search", "", 3, known_hh_ids=set()
            )

        new_results = [r for r in results if not r.get("cached")]
        assert len(new_results) == 3

    @pytest.mark.asyncio
    async def test_batch_fetches_vacancies_concurrently(self):
        """parse_vacancy_page is called in batches via asyncio.gather, not sequentially."""
        service = HHParserService(vacancy_fetch_concurrency=5)

        collected = [
            {"url": f"https://hh.ru/vacancy/{i}", "title": f"Dev {i}", "hh_vacancy_id": str(i)}
            for i in range(5)
        ]

        with (
            patch.object(
                service._scraper, "collect_vacancy_urls", new_callable=AsyncMock
            ) as mock_collect,
            patch.object(
                service._scraper, "parse_vacancy_page", new_callable=AsyncMock
            ) as mock_parse,
        ):
            mock_collect.return_value = collected
            mock_parse.return_value = {
                "description": "d",
                "skills": [],
                "orm_fields": {},
                "employer_data": {},
            }

            results = await service.parse_vacancies(
                "https://hh.ru/search", "", 5, known_hh_ids=set()
            )

        assert mock_parse.await_count == 5
        new_results = [r for r in results if not r.get("cached")]
        assert len(new_results) == 5

    @pytest.mark.asyncio
    async def test_collect_vacancy_urls_called_with_target_count_and_blacklist(self):
        """Scraper receives target_count (not target_count + len(known)) and known as blacklist."""
        service = HHParserService()
        collected = [
            {"url": "https://hh.ru/vacancy/1", "title": "Dev 1", "hh_vacancy_id": "1"},
        ]
        known = {"cached_1", "cached_2"}

        with (
            patch.object(
                service._scraper, "collect_vacancy_urls", new_callable=AsyncMock
            ) as mock_collect,
            patch.object(
                service._scraper, "parse_vacancy_page", new_callable=AsyncMock
            ) as mock_parse,
        ):
            mock_collect.return_value = collected
            mock_parse.return_value = {
                "description": "d",
                "skills": [],
                "orm_fields": {},
                "employer_data": {},
            }

            await service.parse_vacancies(
                "https://hh.ru/search", "python", 50, known_hh_ids=known
            )

        mock_collect.assert_called_once_with(
            "https://hh.ru/search",
            "python",
            50,
            blacklisted_ids=known,
        )
