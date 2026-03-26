from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from bs4 import BeautifulSoup

from src.services.parser.scraper import (
    HHCaptchaRequiredError,
    HHScraper,
    _hh_error_body_has_captcha,
)


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
            items, seen, blacklisted=set(), known_ids=set(), collected=collected, target_count=10
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
            items,
            seen,
            blacklisted={"1", "2"},
            known_ids=set(),
            collected=collected,
            target_count=10,
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
            [item], seen, blacklisted={"1"}, known_ids=set(), collected=collected, target_count=10
        )

        assert new_count == 0
        assert had_unseen is False
        assert blacklisted_skipped == 0

    def test_stops_at_target_count(self):
        collected: list = []
        seen: set = set()
        items = [self._make_item(str(i)) for i in range(5)]

        new_count, _, _ = HHScraper._collect_new_from_page(
            items, seen, blacklisted=set(), known_ids=set(), collected=collected, target_count=3
        )

        assert new_count == 3
        assert len(collected) == 3

    def test_zero_new_count_when_all_blacklisted(self):
        """All blacklisted: new_count=0, blacklisted_skipped reflects them."""
        collected: list = []
        seen: set = set()
        items = [self._make_item("1"), self._make_item("2")]

        new_count, had_unseen, blacklisted_skipped = HHScraper._collect_new_from_page(
            items,
            seen,
            blacklisted={"1", "2"},
            known_ids=set(),
            collected=collected,
            target_count=10,
        )

        assert new_count == 0
        assert had_unseen is True
        assert blacklisted_skipped == 2
        assert len(collected) == 0

    def test_includes_known_ids_in_collected_without_counting_toward_target(self):
        """Vacancies in known_ids are added to collected but do not increment new_count."""
        collected: list = []
        seen: set = set()
        items = [
            self._make_item("1"),
            self._make_item("2"),
            self._make_item("3"),
        ]

        new_count, _, blacklisted_skipped = HHScraper._collect_new_from_page(
            items,
            seen,
            blacklisted=set(),
            known_ids={"1", "3"},
            collected=collected,
            target_count=10,
        )

        assert new_count == 1
        assert blacklisted_skipped == 0
        assert len(collected) == 3
        assert {c["hh_vacancy_id"] for c in collected} == {"1", "2", "3"}


class TestCollectVacancyUrls:
    """Tests for collect_vacancy_urls pagination and stop conditions."""

    @pytest.mark.asyncio
    async def test_stops_when_api_returns_empty_items(
        self, sample_vacancy_api_response: dict
    ) -> None:
        """Stops when the API returns a page with no vacancy items."""
        scraper = HHScraper()
        empty_response = {**sample_vacancy_api_response, "items": []}
        mock_fetch = AsyncMock(side_effect=[sample_vacancy_api_response, empty_response])

        with patch.object(scraper, "_fetch_vacancy_search_page", mock_fetch):
            result = await scraper.collect_vacancy_urls(
                "https://hh.ru/search/vacancy?text=python",
                keyword="",
                target_count=10,
            )

        assert len(result) == 2
        assert mock_fetch.call_count == 2


class TestCollectVacancyUrlsBatch:
    """Tests for collect_vacancy_urls_batch (incremental fetching for compat flow)."""

    @pytest.mark.asyncio
    async def test_returns_urls_next_page_and_has_more(
        self, sample_vacancy_api_response: dict
    ) -> None:
        """Returns (urls, next_page, has_more) tuple."""
        scraper = HHScraper()
        mock_fetch = AsyncMock(return_value=sample_vacancy_api_response)

        with patch.object(scraper, "_fetch_vacancy_search_page", mock_fetch):
            urls, next_page, has_more = await scraper.collect_vacancy_urls_batch(
                base_url="https://hh.ru/search/vacancy?text=python",
                keyword="",
                batch_size=10,
                start_page=0,
                blacklisted_ids=None,
                exclude_ids=None,
            )

        assert isinstance(urls, list)
        assert isinstance(next_page, int)
        assert isinstance(has_more, bool)
        assert next_page >= 0

    @pytest.mark.asyncio
    async def test_exclude_ids_skips_those_vacancies(
        self, sample_vacancy_api_response: dict
    ) -> None:
        """Vacancies in exclude_ids are not included in the result."""
        scraper = HHScraper()
        mock_fetch = AsyncMock(return_value=sample_vacancy_api_response)

        with patch.object(scraper, "_fetch_vacancy_search_page", mock_fetch):
            urls, _, _ = await scraper.collect_vacancy_urls_batch(
                base_url="https://hh.ru/search/vacancy?text=python",
                keyword="",
                batch_size=10,
                start_page=0,
                blacklisted_ids=None,
                exclude_ids={"12345", "67890"},
            )

        returned_ids = {u["hh_vacancy_id"] for u in urls}
        assert "12345" not in returned_ids
        assert "67890" not in returned_ids

    @pytest.mark.asyncio
    async def test_has_more_false_when_no_pages(self) -> None:
        """has_more is False when no vacancy items on page."""
        scraper = HHScraper()
        empty_api_response = {"items": [], "pages": 0, "page": 0, "per_page": 50}
        mock_fetch = AsyncMock(return_value=empty_api_response)

        with patch.object(scraper, "_fetch_vacancy_search_page", mock_fetch):
            urls, next_page, has_more = await scraper.collect_vacancy_urls_batch(
                base_url="https://hh.ru/search/vacancy?text=python",
                keyword="",
                batch_size=10,
                start_page=0,
            )

        assert urls == []
        assert has_more is False

    @pytest.mark.asyncio
    async def test_does_not_fetch_beyond_last_page_index(
        self, sample_vacancy_api_response: dict
    ) -> None:
        """HH API page is 0-based; pages=N means valid indices 0..N-1 — no request for page=N."""
        scraper = HHScraper()
        page_data = {**sample_vacancy_api_response, "pages": 2}
        mock_fetch = AsyncMock(side_effect=[page_data, page_data])

        with patch.object(scraper, "_fetch_vacancy_search_page", mock_fetch):
            await scraper.collect_vacancy_urls(
                "https://hh.ru/search/vacancy?text=python",
                keyword="",
                target_count=50,
            )

        assert mock_fetch.call_count == 2


class TestBuildPageUrl:
    def test_adds_page_param(self):
        url = HHScraper._build_page_url("https://hh.ru/search/vacancy?text=Python", 3)
        assert "page=3" in url
        assert "text=Python" in url

    def test_replaces_existing_page(self):
        url = HHScraper._build_page_url("https://hh.ru/search/vacancy?text=Python&page=0", 5)
        assert "page=5" in url
        assert "page=0" not in url


class TestBuildApiUrl:
    def test_converts_to_api_base(self):
        url = HHScraper._build_api_url("https://izhevsk.hh.ru/search/vacancy?text=Backend", page=0)
        assert url.startswith("https://api.hh.ru/vacancies")
        assert "text=Backend" in url
        assert "page=0" in url
        assert "per_page=50" in url

    def test_preserves_filter_params(self):
        base = "https://hh.ru/search/vacancy?text=Python&area=113&employment_form=FULL"
        url = HHScraper._build_api_url(base, page=2, per_page=20)
        assert "text=Python" in url
        assert "area=113" in url
        assert "employment_form=FULL" in url
        assert "page=2" in url
        assert "per_page=20" in url

    def test_drops_unsupported_params(self):
        base = "https://hh.ru/search/vacancy?text=Python&hhtmFrom=vacancy_search_list"
        url = HHScraper._build_api_url(base, page=0)
        assert "hhtmFrom" not in url
        assert "text=Python" in url

    def test_overwrites_existing_page_and_per_page_params(self):
        base = "https://hh.ru/search/vacancy?text=python&page=0&per_page=10"
        url = HHScraper._build_api_url(base, page=2, per_page=20)
        assert "text=python" in url
        assert "page=2" in url
        assert "per_page=20" in url
        assert "page=0" not in url
        assert "per_page=10" not in url


class TestExtractVacanciesFromApiResponse:
    def test_extracts_vacancies_with_matching_keyword(self, sample_vacancy_api_response: dict):
        scraper = HHScraper()
        results = scraper._extract_vacancies_from_api_response(
            sample_vacancy_api_response, "frontend"
        )
        assert len(results) == 1
        assert results[0]["title"] == "Frontend Developer"
        assert results[0]["hh_vacancy_id"] == "12345"
        assert results[0]["url"] == "https://hh.ru/vacancy/12345"
        assert results[0]["company_name"] == "Yandex"
        assert "300 000" in results[0]["salary"]
        assert "руб." in results[0]["salary"]

    def test_extracts_all_vacancies_without_keyword(self, sample_vacancy_api_response: dict):
        scraper = HHScraper()
        results = scraper._extract_vacancies_from_api_response(sample_vacancy_api_response, "")
        assert len(results) == 2

    def test_returns_empty_for_no_matches(self, sample_vacancy_api_response: dict):
        scraper = HHScraper()
        results = scraper._extract_vacancies_from_api_response(
            sample_vacancy_api_response, "devops"
        )
        assert len(results) == 0

    def test_cleans_url_query_params(self, sample_vacancy_api_response: dict):
        scraper = HHScraper()
        results = scraper._extract_vacancies_from_api_response(
            sample_vacancy_api_response, "frontend"
        )
        assert "?" not in results[0]["url"]

    def test_matches_keyword_in_snippet_when_not_in_title(self):
        """Vacancy with keyword in snippet but not in name is included."""
        api_response = {
            "items": [
                {
                    "id": "131299561",
                    "name": "PHP-разработчик",
                    "alternate_url": "https://hh.ru/vacancy/131299561",
                    "employer": {
                        "name": "SHEVEREV",
                        "alternate_url": "https://hh.ru/employer/5362384",
                    },
                    "snippet": {
                        "requirement": "Коммерческий опыт backend-разработки на PHP от 3 лет.",
                        "responsibility": "Разработка backend-сервисов на PHP/Laravel.",
                    },
                },
            ],
            "found": 1,
            "pages": 1,
            "page": 0,
            "per_page": 50,
        }
        scraper = HHScraper()
        results = scraper._extract_vacancies_from_api_response(api_response, "Backend")
        assert len(results) == 1
        assert results[0]["hh_vacancy_id"] == "131299561"
        assert results[0]["title"] == "PHP-разработчик"


class TestExtractVacancyId:
    def test_extracts_id_from_url(self):
        assert HHScraper._extract_vacancy_id("https://hh.ru/vacancy/12345") == "12345"

    def test_extracts_id_from_regional_url(self):
        assert HHScraper._extract_vacancy_id("https://izhevsk.hh.ru/vacancy/67890") == "67890"

    def test_returns_none_for_invalid_url(self):
        assert HHScraper._extract_vacancy_id("https://example.com/page") is None


@pytest.fixture
def sample_vacancy_detail_api_response() -> dict:
    """HH.ru API vacancy detail response."""
    return {
        "id": "1",
        "name": "Python Developer",
        "description": "<p>Python developer needed. Django experience required.</p>",
        "key_skills": [
            {"name": "Python"},
            {"name": "Django"},
            {"name": "PostgreSQL"},
        ],
        "employer": {"id": "123", "name": "Acme Corp"},
        "area": {"id": "1", "name": "Москва", "url": "https://api.hh.ru/areas/1"},
        "experience": {"id": "between1And3", "name": "1–3 года"},
        "schedule": {"id": "fullDay", "name": "Полный день"},
        "employment": {"id": "full", "name": "Полная занятость"},
    }


class TestParseVacancyPage:
    @pytest.mark.asyncio
    async def test_extracts_description_and_skills(self, sample_vacancy_detail_api_response: dict):
        scraper = HHScraper()
        mock_client = AsyncMock()

        with patch.object(scraper, "fetch_vacancy_by_id", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = sample_vacancy_detail_api_response
            result = await scraper.parse_vacancy_page(mock_client, "https://hh.ru/vacancy/1")

        assert "Python" in result["description"]
        assert "Django" in result["description"]
        assert "Python" in result["skills"]
        assert "Django" in result["skills"]
        assert "PostgreSQL" in result["skills"]
        assert "employer_data" in result
        assert "area_data" in result
        assert "orm_fields" in result
        assert result["employer_data"].get("id") == str(
            sample_vacancy_detail_api_response["employer"]["id"]
        )
        assert result["area_data"].get("id") == str(
            sample_vacancy_detail_api_response["area"]["id"]
        )

    @pytest.mark.asyncio
    async def test_returns_empty_on_failed_fetch(self):
        scraper = HHScraper()
        mock_client = AsyncMock()

        with patch.object(
            scraper, "fetch_vacancy_by_id", new_callable=AsyncMock, return_value=None
        ):
            result = await scraper.parse_vacancy_page(mock_client, "https://hh.ru/vacancy/1")

        assert result == {}


class TestHHScraperHeaders:
    def test_headers_api_sets_user_agent_and_hh_user_agent_from_pool_or_settings(
        self, monkeypatch
    ):
        from src.config import settings

        monkeypatch.setattr(settings, "hh_user_agent", "UnitTest/1.0 (test@example.com)")
        scraper = HHScraper(page_delay=(0, 0), vacancy_delay=(0, 0))
        with patch(
            "src.services.parser.scraper.random.choice",
            return_value="UnitTest/1.0 (test@example.com)",
        ):
            headers = scraper._headers_api()
        assert headers["User-Agent"] == "UnitTest/1.0 (test@example.com)"
        assert headers["HH-User-Agent"] == "UnitTest/1.0 (test@example.com)"

    def test_headers_html_sets_user_agent_and_hh_user_agent_from_pool_or_settings(
        self, monkeypatch
    ):
        from src.config import settings

        monkeypatch.setattr(settings, "hh_user_agent", "UnitTest/2.0 (test@example.com)")
        scraper = HHScraper(page_delay=(0, 0), vacancy_delay=(0, 0))
        with patch(
            "src.services.parser.scraper.random.choice",
            return_value="UnitTest/2.0 (test@example.com)",
        ):
            headers = scraper._headers()
        assert headers["User-Agent"] == "UnitTest/2.0 (test@example.com)"
        assert headers["HH-User-Agent"] == "UnitTest/2.0 (test@example.com)"


class TestHHCaptchaAndPublicApiBreaker:
    def test_hh_error_body_has_captcha_type(self):
        body = '{"errors":[{"type":"captcha_required","captcha_url":"https://hh.ru/captcha"}]}'
        assert _hh_error_body_has_captcha(body) is True

    def test_hh_error_body_has_captcha_value(self):
        assert _hh_error_body_has_captcha('{"errors":[{"value":"captcha_required"}]}') is True

    def test_hh_error_body_has_captcha_false_non_json(self):
        assert _hh_error_body_has_captcha("not json") is False

    def test_hh_error_body_has_captcha_false_other_error(self):
        assert _hh_error_body_has_captcha('{"errors":[{"type":"not_found"}]}') is False

    @pytest.mark.asyncio
    async def test_fetch_api_page_captcha_no_retry_single_http_call(self):
        calls: list[object] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(
                403,
                json={
                    "errors": [
                        {
                            "type": "captcha_required",
                            "captcha_url": "https://hh.ru/account/captcha",
                        }
                    ]
                },
            )

        transport = httpx.MockTransport(handler)
        mock_br = MagicMock()
        mock_br.is_call_allowed.return_value = True
        scraper = HHScraper(
            public_api_breaker=mock_br,
            page_delay=(0, 0),
            vacancy_delay=(0, 0),
        )
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(HHCaptchaRequiredError):
                await scraper._fetch_api_page(client, "https://api.hh.ru/vacancies/1")
        assert len(calls) == 1
        mock_br.record_failure.assert_called_once()
        mock_br.record_success.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_api_page_circuit_open_skips_http(self):
        mock_br = MagicMock()
        mock_br.is_call_allowed.return_value = False
        scraper = HHScraper(
            public_api_breaker=mock_br,
            page_delay=(0, 0),
            vacancy_delay=(0, 0),
        )
        client = AsyncMock()
        client.get = AsyncMock(side_effect=AssertionError("GET must not be called"))
        with pytest.raises(HHCaptchaRequiredError) as exc_info:
            await scraper._fetch_api_page(client, "https://api.hh.ru/vacancies/1")
        assert "circuit" in str(exc_info.value).lower()
        client.get.assert_not_called()
        mock_br.record_failure.assert_not_called()
