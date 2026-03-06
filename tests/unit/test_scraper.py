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
            desc, skills = await scraper.parse_vacancy_page(mock_client, "https://hh.ru/vacancy/1")

        assert "Python" in desc
        assert "Django" in desc
        assert "Python" in skills
        assert "Django" in skills
        assert "PostgreSQL" in skills

    @pytest.mark.asyncio
    async def test_returns_empty_on_failed_fetch(self):
        scraper = HHScraper()
        mock_client = AsyncMock()

        with patch.object(scraper, "_fetch_page", return_value=None):
            desc, skills = await scraper.parse_vacancy_page(mock_client, "https://hh.ru/vacancy/1")

        assert desc == ""
        assert skills == []
