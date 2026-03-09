from unittest.mock import AsyncMock, patch

import pytest
from bs4 import BeautifulSoup

from src.services.parser.scraper import HHScraper


class TestExtractCardMetadata:
    def setup_method(self):
        self.scraper = HHScraper()

    def test_extracts_company_name_and_url(self, sample_vacancy_html: str):
        soup = BeautifulSoup(sample_vacancy_html, "html.parser")
        results = self.scraper._extract_vacancies_from_page(soup, "frontend")
        assert len(results) == 1
        assert results[0].get("company_name") == "Yandex"
        assert results[0].get("company_url") == "https://hh.ru/employer/100"

    def test_extracts_salary(self, sample_vacancy_html: str):
        soup = BeautifulSoup(sample_vacancy_html, "html.parser")
        results = self.scraper._extract_vacancies_from_page(soup, "frontend")
        assert results[0].get("salary") == "300 000 руб."

    def test_extracts_tags(self, sample_vacancy_html: str):
        soup = BeautifulSoup(sample_vacancy_html, "html.parser")
        results = self.scraper._extract_vacancies_from_page(soup, "frontend")
        tags = results[0].get("tags", [])
        assert "Remote" in tags

    def test_no_salary_when_missing(self, sample_vacancy_html: str):
        soup = BeautifulSoup(sample_vacancy_html, "html.parser")
        results = self.scraper._extract_vacancies_from_page(soup, "backend")
        assert results[0].get("salary") is None


class TestParseVacancyPageEnhanced:
    @pytest.mark.asyncio
    async def test_extracts_detail_fields(self, sample_vacancy_page_html: str):
        scraper = HHScraper()
        mock_client = AsyncMock()

        with patch.object(scraper, "_fetch_page") as mock_fetch:
            mock_fetch.return_value = BeautifulSoup(sample_vacancy_page_html, "html.parser")
            result = await scraper.parse_vacancy_page(mock_client, "https://hh.ru/vacancy/1")

        assert isinstance(result, dict)
        assert "Python" in result["description"]
        assert "Python" in result["skills"]
        assert result["compensation_frequency"] == "Monthly"
        assert result["work_experience"] == "3-6 years"
        assert result["employment_type"] == "Full-time"
        assert result["work_schedule"] == "5/2"
        assert result["working_hours"] == "8 hours"
        assert result["work_formats"] == "Remote"

    @pytest.mark.asyncio
    async def test_returns_empty_dict_on_failure(self):
        scraper = HHScraper()
        mock_client = AsyncMock()

        with patch.object(scraper, "_fetch_page", return_value=None):
            result = await scraper.parse_vacancy_page(mock_client, "https://hh.ru/vacancy/1")

        assert result == {}
