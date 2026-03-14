from unittest.mock import AsyncMock, patch

import pytest
from bs4 import BeautifulSoup

from src.services.parser.scraper import HHScraper, _looks_like_salary, _strip_field_prefix


class TestLooksLikeSalary:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("300 000 руб.", True),
            ("от 100 000 ₽ в месяц, до вычета налогов", True),
            ("до 200 $ за месяц", True),
            ("от 4 000 € в год", True),
            ("Сейчас смотрят 6 человек", False),
            ("Сейчас смотрит 1 человек", False),
            ("2.6", False),
            ("42", False),
            ("", False),
        ],
    )
    def test_identifies_salary_text_correctly(self, text: str, expected: bool):
        assert _looks_like_salary(text) is expected


class TestStripFieldPrefix:
    @pytest.mark.parametrize(
        "field,text,expected",
        [
            ("compensation_frequency", "Оплата:ежемесячно", "ежемесячно"),
            ("compensation_frequency", "Оплата: раз в две недели", "раз в две недели"),
            ("compensation_frequency", "Monthly", "Monthly"),
            ("work_formats", "Формат работы:удалённо", "удалённо"),
            ("work_formats", "Формат работы: удалённо или гибрид", "удалённо или гибрид"),
            ("work_formats", "Remote", "Remote"),
            ("work_experience", "Опыт работы:1–3 года", "1–3 года"),
            ("employment_type", "Занятость:полная", "полная"),
            ("working_hours", "8 часов", "8 часов"),
            ("unknown_field", "Формат работы:удалённо", "Формат работы:удалённо"),
        ],
    )
    def test_strips_known_label_prefix(self, field: str, text: str, expected: str):
        assert _strip_field_prefix(field, text) == expected


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

    def test_viewer_count_is_not_stored_as_salary(self, vacancy_html_with_viewer_count: str):
        soup = BeautifulSoup(vacancy_html_with_viewer_count, "html.parser")
        results = self.scraper._extract_vacancies_from_page(soup, "")
        assert results[0].get("salary") is None

    def test_company_rating_is_not_stored_as_salary(self, vacancy_html_with_rating: str):
        soup = BeautifulSoup(vacancy_html_with_rating, "html.parser")
        results = self.scraper._extract_vacancies_from_page(soup, "")
        assert results[0].get("salary") is None

    def test_multi_span_salary_has_spaces_between_parts(
        self, vacancy_html_with_multi_span_salary: str
    ):
        soup = BeautifulSoup(vacancy_html_with_multi_span_salary, "html.parser")
        results = self.scraper._extract_vacancies_from_page(soup, "")
        salary = results[0].get("salary", "")
        assert salary == "от 4 000 $ за месяц"


def _api_response_detail(
    description: str = "Python developer needed. Django experience required.",
    skills: list | None = None,
    work_experience: str = "3-6 years",
    work_schedule: str = "5/2",
    working_hours: str = "8 hours",
    work_formats: str = "Remote",
    compensation_frequency: str = "Monthly",
) -> dict:
    """HH API vacancy detail response for parse_vacancy_page tests."""
    skills = skills or ["Python", "Django", "PostgreSQL"]
    return {
        "name": "Python Developer",
        "description": f"<p>{description}</p>",
        "key_skills": [{"name": s} for s in skills],
        "employer": {"id": "123", "name": "Acme Corp"},
        "area": {"id": "1", "name": "Москва"},
        "experience": {"id": "between3And6", "name": work_experience},
        "schedule": {"id": "fullDay", "name": "Полный день"},
        "employment": {"id": "full", "name": "Full-time"},
        "work_schedule_by_days": [{"id": "FIVE_ON_TWO_OFF", "name": work_schedule}],
        "working_hours": [{"id": "HOURS_8", "name": working_hours}],
        "work_format": [{"id": "REMOTE", "name": work_formats}],
        "salary": {"from": 100000, "to": 200000, "currency": "RUR", "period": compensation_frequency},
    }


class TestParseVacancyPageEnhanced:
    @pytest.mark.asyncio
    async def test_extracts_detail_fields(self):
        """parse_vacancy_page uses fetch_vacancy_by_id (API), not HTML parsing."""
        scraper = HHScraper()
        mock_client = AsyncMock()
        api_response = _api_response_detail()

        with patch.object(scraper, "fetch_vacancy_by_id", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = api_response
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

        with patch.object(scraper, "fetch_vacancy_by_id", new_callable=AsyncMock, return_value=None):
            result = await scraper.parse_vacancy_page(mock_client, "https://hh.ru/vacancy/1")

        assert result == {}

    @pytest.mark.asyncio
    async def test_strips_work_formats_label_prefix(self):
        """work_formats from API work_format array (no HTML prefix stripping)."""
        scraper = HHScraper()
        mock_client = AsyncMock()
        api_response = _api_response_detail(work_formats="удалённо")

        with patch.object(scraper, "fetch_vacancy_by_id", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = api_response
            result = await scraper.parse_vacancy_page(mock_client, "https://hh.ru/vacancy/1")

        assert result["work_formats"] == "удалённо"

    @pytest.mark.asyncio
    async def test_strips_work_experience_label_prefix(self):
        """work_experience from API experience.name (no HTML prefix stripping)."""
        scraper = HHScraper()
        mock_client = AsyncMock()
        api_response = _api_response_detail(work_experience="1–3 года")

        with patch.object(scraper, "fetch_vacancy_by_id", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = api_response
            result = await scraper.parse_vacancy_page(mock_client, "https://hh.ru/vacancy/1")

        assert result["work_experience"] == "1–3 года"

    @pytest.mark.asyncio
    async def test_strips_compensation_frequency_label_prefix(self):
        """compensation_frequency from API salary.period (no HTML prefix stripping)."""
        scraper = HHScraper()
        mock_client = AsyncMock()
        api_response = _api_response_detail(compensation_frequency="ежемесячно")

        with patch.object(scraper, "fetch_vacancy_by_id", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = api_response
            result = await scraper.parse_vacancy_page(mock_client, "https://hh.ru/vacancy/1")

        assert result["compensation_frequency"] == "ежемесячно"
