from unittest.mock import AsyncMock, patch

import pytest
from bs4 import BeautifulSoup

from src.services.parser.scraper import HHScraper


class TestExtractVacanciesFromPage:
    def setup_method(self):
        self.scraper = HHScraper()

    def test_extracts_vacancies_with_matching_keyword(self, sample_vacancy_html: str):
        soup = BeautifulSoup(sample_vacancy_html, "html.parser")
        results = self.scraper._extract_vacancies_from_page(soup, "frontend")
        assert len(results) == 1
        assert results[0]["title"] == "Frontend Developer"
        assert results[0]["hh_vacancy_id"] == "12345"

    def test_extracts_all_vacancies_without_keyword(self, sample_vacancy_html: str):
        soup = BeautifulSoup(sample_vacancy_html, "html.parser")
        results = self.scraper._extract_vacancies_from_page(soup, "")
        assert len(results) == 2

    def test_returns_empty_for_no_matches(self, sample_vacancy_html: str):
        soup = BeautifulSoup(sample_vacancy_html, "html.parser")
        results = self.scraper._extract_vacancies_from_page(soup, "devops")
        assert len(results) == 0

    def test_cleans_url_query_params(self, sample_vacancy_html: str):
        soup = BeautifulSoup(sample_vacancy_html, "html.parser")
        results = self.scraper._extract_vacancies_from_page(soup, "frontend")
        assert "?" not in results[0]["url"]


class TestCollectNewFromPage:
    def _make_item(self, vacancy_id: str) -> dict:
        return {
            "url": f"https://hh.ru/vacancy/{vacancy_id}",
            "title": f"Vacancy {vacancy_id}",
            "hh_vacancy_id": vacancy_id,
        }

    def test_adds_unseen_non_blacklisted_items(self):
        collected: list = []
        seen: set = set()
        items = [self._make_item("1"), self._make_item("2")]

        new_count, had_unseen, blacklisted_skipped = HHScraper._collect_new_from_page(
            items, seen, blacklisted=set(), collected=collected, target_count=10
        )

        assert new_count == 2
        assert had_unseen is True
        assert blacklisted_skipped == 0
        assert len(collected) == 2

    def test_counts_blacklisted_items_separately(self):
        collected: list = []
        seen: set = set()
        items = [self._make_item("1"), self._make_item("2"), self._make_item("3")]

        new_count, had_unseen, blacklisted_skipped = HHScraper._collect_new_from_page(
            items, seen, blacklisted={"1", "2"}, collected=collected, target_count=10
        )

        assert new_count == 1
        assert had_unseen is True
        assert blacklisted_skipped == 2
        assert len(collected) == 1

    def test_skips_already_seen_urls_without_counting_as_blacklisted(self):
        item = self._make_item("1")
        seen = {item["url"]}
        collected: list = []

        new_count, had_unseen, blacklisted_skipped = HHScraper._collect_new_from_page(
            [item], seen, blacklisted={"1"}, collected=collected, target_count=10
        )

        assert new_count == 0
        assert had_unseen is False
        assert blacklisted_skipped == 0

    def test_stops_at_target_count(self):
        collected: list = []
        seen: set = set()
        items = [self._make_item(str(i)) for i in range(5)]

        new_count, _, _ = HHScraper._collect_new_from_page(
            items, seen, blacklisted=set(), collected=collected, target_count=3
        )

        assert new_count == 3
        assert len(collected) == 3

    def test_zero_pages_increments_when_all_blacklisted(self):
        """When all keyword matches are blacklisted, new_count=0 so zero_pages increments."""
        collected: list = []
        seen: set = set()
        items = [self._make_item("1"), self._make_item("2")]

        new_count, had_unseen, blacklisted_skipped = HHScraper._collect_new_from_page(
            items, seen, blacklisted={"1", "2"}, collected=collected, target_count=10
        )

        assert new_count == 0
        assert had_unseen is True
        assert blacklisted_skipped == 2
        assert len(collected) == 0


class TestCollectVacancyUrls:
    """Tests for collect_vacancy_urls pagination and stop conditions."""

    @pytest.mark.asyncio
    async def test_stops_after_three_pages_all_blacklisted(
        self, sample_vacancy_html: str
    ) -> None:
        """Stops after 3 consecutive pages that add nothing (e.g. all blacklisted)."""
        scraper = HHScraper()
        soup = BeautifulSoup(sample_vacancy_html, "html.parser")
        blacklisted = {"12345", "67890"}  # all IDs from sample_vacancy_html
        mock_fetch = AsyncMock(return_value=soup)

        with patch.object(scraper, "_fetch_page", mock_fetch):
            result = await scraper.collect_vacancy_urls(
                "https://hh.ru/search/vacancy?text=python",
                keyword="",
                target_count=10,
                blacklisted_ids=blacklisted,
            )

        assert result == []
        assert mock_fetch.call_count == 3


class TestBuildPageUrl:
    def test_adds_page_param(self):
        url = HHScraper._build_page_url("https://hh.ru/search/vacancy?text=Python", 3)
        assert "page=3" in url
        assert "text=Python" in url

    def test_replaces_existing_page(self):
        url = HHScraper._build_page_url("https://hh.ru/search/vacancy?text=Python&page=0", 5)
        assert "page=5" in url
        assert "page=0" not in url


class TestExtractVacancyId:
    def test_extracts_id_from_url(self):
        assert HHScraper._extract_vacancy_id("https://hh.ru/vacancy/12345") == "12345"

    def test_extracts_id_from_regional_url(self):
        assert HHScraper._extract_vacancy_id("https://izhevsk.hh.ru/vacancy/67890") == "67890"

    def test_returns_none_for_invalid_url(self):
        assert HHScraper._extract_vacancy_id("https://example.com/page") is None


class TestParseVacancyPage:
    @pytest.mark.asyncio
    async def test_extracts_description_and_skills(self, sample_vacancy_page_html: str):
        scraper = HHScraper()
        mock_client = AsyncMock()

        with patch.object(scraper, "_fetch_page") as mock_fetch:
            mock_fetch.return_value = BeautifulSoup(sample_vacancy_page_html, "html.parser")
            result = await scraper.parse_vacancy_page(mock_client, "https://hh.ru/vacancy/1")

        assert "Python" in result["description"]
        assert "Django" in result["description"]
        assert "Python" in result["skills"]
        assert "Django" in result["skills"]
        assert "PostgreSQL" in result["skills"]

    @pytest.mark.asyncio
    async def test_returns_empty_on_failed_fetch(self):
        scraper = HHScraper()
        mock_client = AsyncMock()

        with patch.object(scraper, "_fetch_page", return_value=None):
            result = await scraper.parse_vacancy_page(mock_client, "https://hh.ru/vacancy/1")

        assert result == {}
