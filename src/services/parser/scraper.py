"""Async HH.ru vacancy scraper.

Replaces synchronous requests-based scraping from the original script
with httpx async client, configurable delays, and blacklist support.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup, Tag

from src.config import settings
from src.core.logging import get_logger
from src.services.hh_ui.applicant_http import url_suggests_login_page
from src.services.hh_ui.config import HhUiApplyConfig
from src.services.hh_ui.runner import (
    fetch_public_hh_api_json_via_browser,
    render_search_page_with_storage,
    render_vacancy_detail_page_with_storage,
)
from src.services.parser.hh_mapper import map_api_vacancy_to_orm_fields
from src.services.parser.keyword_match import matches_keyword_expression
from src.worker.circuit_breaker import CircuitBreaker

logger = get_logger(__name__)

HH_VACANCY_RE = re.compile(r"https?://(?:[a-z]+\.)?hh\.ru/vacancy/(\d+)")
SALARY_CLASS_RE = re.compile(r"magritte-text___")

_SALARY_CURRENCY_MARKERS: tuple[str, ...] = ("₽", "$", "€", "руб")

_DETAIL_FIELD_PREFIXES: dict[str, str] = {
    "compensation_frequency": "Оплата:",
    "work_formats": "Формат работы:",
    "work_experience": "Опыт работы:",
    "employment_type": "Занятость:",
    "work_schedule": "График работы:",
    "working_hours": "Рабочие часы:",
}

_MULTI_SPACE_RE = re.compile(r" {2,}")
_MAX_PAGES = 100  # Up to 100 pages × 100 per_page (HH API max per page)
# HH search list: retry same page (transient 403/429/5xx); do not unbound-block workers.
_SEARCH_LIST_MAX_ATTEMPTS = 30
_SEARCH_LIST_BODY_LOG_LEN = 800
HH_API_BASE = "https://api.hh.ru/vacancies"
_API_UNSUPPORTED_PARAMS = frozenset(
    {"hhtmFrom", "hhtmFromLabel", "L_save_area", "ored_clusters", "enable_snippets", "search_field"}
)

_hh_public_api_breaker_singleton: CircuitBreaker | None = None
_RU_DATE_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")

# Rotated per request with settings.hh_user_agent — reduces identical fingerprint on public API.
_HH_BROWSER_USER_AGENTS: tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
)


class HHCaptchaRequiredError(Exception):
    """HeadHunter returned captcha_required or the public API circuit is open."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _hh_error_body_has_captcha(body: str) -> bool:
    """True when HH JSON error payload indicates captcha_required."""
    if not body or "captcha" not in body.lower():
        return False
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return False
    errors = data.get("errors")
    if not isinstance(errors, list):
        return False
    for err in errors:
        if not isinstance(err, dict):
            continue
        if err.get("type") == "captcha_required":
            return True
        if err.get("value") == "captcha_required":
            return True
    return False


def _hh_vacancy_detail_json_is_valid(data: dict) -> bool:
    """True when JSON from api.hh.ru/vacancies/{{id}} looks like a vacancy object."""
    if not isinstance(data, dict):
        return False
    if data.get("id") is not None or isinstance(data.get("name"), str):
        return True
    return "description" in data


def _synthetic_search_api_payload_from_web_cards(page_results: list[dict]) -> dict:
    """Build an API-shaped dict so _extract_vacancies_from_api_response can run unchanged."""
    items: list[dict] = []
    for card in page_results:
        items.append(
            {
                "id": card["hh_vacancy_id"],
                "name": card["title"],
                "alternate_url": card["url"],
                "snippet": {"requirement": "", "responsibility": ""},
                "employer": {
                    "name": card.get("company_name"),
                    "alternate_url": card.get("company_url"),
                },
                "salary": None,
                "work_format": [],
                "schedule": None,
            }
        )
    return {"items": items, "pages": _MAX_PAGES}


def _get_hh_public_api_breaker() -> CircuitBreaker:
    """Redis-backed breaker shared across workers; exponential recovery between opens."""
    global _hh_public_api_breaker_singleton
    if _hh_public_api_breaker_singleton is None:
        _hh_public_api_breaker_singleton = CircuitBreaker(
            "hh_public_api",
            failure_threshold=settings.hh_public_api_circuit_failure_threshold,
            recovery_timeout=settings.hh_public_api_circuit_recovery_seconds,
            exponential_recovery=True,
            recovery_multiplier=settings.hh_public_api_circuit_recovery_multiplier,
            max_recovery_timeout=settings.hh_public_api_circuit_recovery_max_seconds,
        )
    return _hh_public_api_breaker_singleton


def _is_public_api_rate_limit_status(status_code: int | None) -> bool:
    """True for 403/429 on public API when not handled as captcha JSON elsewhere."""
    return status_code in (403, 429)


def _looks_like_salary(text: str) -> bool:
    """Return True only when *text* contains a currency marker.

    HH.ru search cards show both salary amounts and viewer-count strings
    (e.g. "Сейчас смотрят 6 человек") inside the same Magritte text class.
    Ratings like "2.6" also match that class.  We accept a string as salary
    only when it carries an explicit currency marker.
    """
    return any(marker in text for marker in _SALARY_CURRENCY_MARKERS)


def _strip_field_prefix(field: str, text: str) -> str:
    """Remove a known Russian label prefix from a scraped detail field value."""
    prefix = _DETAIL_FIELD_PREFIXES.get(field, "")
    if prefix and text.startswith(prefix):
        return text[len(prefix) :].strip()
    return text


_CURRENCY_SYMBOLS: dict[str, str] = {
    "RUR": "руб.",
    "RUB": "руб.",
    "USD": "$",
    "EUR": "€",
    "UZS": "сум",
}


def _format_api_salary(salary: dict | None) -> str:
    """Format HH.ru API salary object to human-readable string."""
    if not salary:
        return ""
    parts: list[str] = []
    if "from" in salary and salary["from"] is not None:
        parts.append(f"{salary['from']:,}".replace(",", " "))
    if "to" in salary and salary["to"] is not None:
        parts.append(f"{salary['to']:,}".replace(",", " "))
    if not parts:
        return ""
    currency = salary.get("currency", "RUR")
    symbol = _CURRENCY_SYMBOLS.get(currency, currency)
    return " – ".join(parts) + " " + symbol


def _html_to_plain_text(html: str) -> str:
    """Strip HTML tags from vacancy description for AI consumption."""
    if not html or not html.strip():
        return ""
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator="\n", strip=True)


def _parse_ru_date(val: str | None) -> datetime | None:
    if not val:
        return None
    match = _RU_DATE_RE.search(val)
    if not match:
        return None
    day, month, year = match.groups()
    try:
        return datetime(int(year), int(month), int(day), tzinfo=UTC).replace(tzinfo=None)
    except ValueError:
        return None


def _clean_text(text: str | None) -> str:
    return _MULTI_SPACE_RE.sub(" ", (text or "").replace("\xa0", " ")).strip()


def _parse_html_title_company_location(title_text: str) -> tuple[str, str, str]:
    title_text = _clean_text(title_text)
    if not title_text:
        return "", "", ""
    prefix = "Вакансия "
    if title_text.startswith(prefix):
        title_text = title_text[len(prefix) :]
    match = re.match(r"(.+?) в (.+?), работа в компании (.+)$", title_text)
    if match:
        return _clean_text(match.group(1)), _clean_text(match.group(3)), _clean_text(match.group(2))
    return title_text, "", ""


def _extract_meta_description_parts(description: str) -> dict[str, str | datetime | None]:
    desc = _clean_text(description)
    if not desc:
        return {
            "salary": "",
            "location": "",
            "experience_name": "",
            "employment_name": "",
            "published_at": None,
        }
    salary_match = re.search(r"Зарплата:\s*([^\.]+)", desc)
    location_match = re.search(
        r"Зарплата:\s*[^\.]+\.\s*([^\.]+)\.\s*Требуемый опыт:",
        desc,
    )
    experience_match = re.search(r"Требуемый опыт:\s*([^\.]+)", desc)
    employment_match = re.search(r"Требуемый опыт:\s*[^\.]+\.\s*([^\.]+)\.", desc)
    published_match = re.search(r"Дата публикации:\s*(\d{2}\.\d{2}\.\d{4})", desc)
    return {
        "salary": _clean_text(salary_match.group(1) if salary_match else ""),
        "location": _clean_text(location_match.group(1) if location_match else ""),
        "experience_name": _clean_text(experience_match.group(1) if experience_match else ""),
        "employment_name": _clean_text(employment_match.group(1) if employment_match else ""),
        "published_at": _parse_ru_date(published_match.group(1) if published_match else desc),
    }


def _extract_detail_field_from_soup(soup: BeautifulSoup, prefix: str) -> str:
    for text_node in soup.find_all(string=True):
        text = _clean_text(str(text_node))
        if not text.startswith(prefix):
            continue
        value = _clean_text(text[len(prefix) :])
        if value:
            return value
        parent = text_node.parent
        if parent is not None:
            parent_text = _clean_text(parent.get_text(" ", strip=True))
            value = _clean_text(parent_text[len(prefix) :]) if parent_text.startswith(prefix) else ""
            if value:
                return value
    return ""


def _extract_company_link(soup: BeautifulSoup) -> str | None:
    for a_tag in soup.find_all("a", href=True):
        href = str(a_tag.get("href") or "")
        if "/employer/" in href:
            return href
    return None


def _vacancy_api_url(vacancy_id: str) -> str:
    """Return the HH API URL for a single vacancy detail."""
    return f"{HH_API_BASE}/{vacancy_id}"


def _map_api_vacancy_to_page_data(api_response: dict, list_item: dict | None = None) -> dict:
    """Map HH API vacancy (list or detail) to page_data shape used by extractor.

    Uses unified mapper for both /vacancies/ (list) and /vacancies/{id} (detail) shapes.
    list_item: optional dict from search list for fields not in detail response.
    """
    list_item = list_item or {}
    mapped = map_api_vacancy_to_orm_fields(api_response)

    description = _html_to_plain_text(api_response.get("description", "") or "")
    key_skills = api_response.get("key_skills") or []
    skills = [s["name"] for s in key_skills if isinstance(s, dict) and s.get("name")]

    employer = api_response.get("employer") or {}
    company_name = employer.get("name") or list_item.get("company_name", "")

    salary = api_response.get("salary") or api_response.get("salary_range")
    salary_str = _format_api_salary(salary) or list_item.get("salary", "")
    compensation_frequency = ""
    if isinstance(salary, dict) and salary.get("period"):
        compensation_frequency = str(salary["period"])

    experience = api_response.get("experience")
    work_experience = experience.get("name", "") if isinstance(experience, dict) else ""

    schedule = api_response.get("schedule")
    work_schedule_by_days = api_response.get("work_schedule_by_days") or []
    if work_schedule_by_days and isinstance(work_schedule_by_days, list):
        first = work_schedule_by_days[0] if work_schedule_by_days else None
        work_schedule = first.get("name", "") if isinstance(first, dict) else ""
    else:
        work_schedule = ""
    if not work_schedule and isinstance(schedule, dict):
        work_schedule = schedule.get("name", "")

    employment = api_response.get("employment")
    employment_type = employment.get("name", "") if isinstance(employment, dict) else ""

    work_formats = api_response.get("work_format") or []
    work_formats_str = ", ".join(
        wf["name"] for wf in work_formats if isinstance(wf, dict) and wf.get("name")
    )

    working_hours = api_response.get("working_hours") or []
    working_hours_str = ", ".join(
        wh["name"] for wh in working_hours if isinstance(wh, dict) and wh.get("name")
    )

    result: dict = {
        "description": description,
        "skills": skills,
        "title": api_response.get("name", "") or list_item.get("title", ""),
        "company_name": company_name,
        "salary": salary_str,
        "work_experience": work_experience,
        "employment_type": employment_type,
        "work_schedule": work_schedule,
        "work_formats": work_formats_str,
        "working_hours": working_hours_str,
        "compensation_frequency": compensation_frequency,
        "employer_data": mapped["employer_data"],
        "area_data": mapped["area_data"],
        "orm_fields": mapped["orm_fields"],
    }
    return result


def _map_html_vacancy_to_page_data(soup: BeautifulSoup, _url: str) -> dict:
    title_tag = soup.find("title")
    meta_desc = soup.find("meta", attrs={"name": "description"})
    title_text = _clean_text(title_tag.get_text(strip=True) if title_tag else "")
    desc_text = _clean_text(meta_desc.get("content") if meta_desc else "")
    parsed_title, parsed_company, parsed_location = _parse_html_title_company_location(title_text)
    meta_parts = _extract_meta_description_parts(desc_text)

    description_el = soup.select_one('[data-qa="vacancy-description"]')
    description = (
        _html_to_plain_text(str(description_el))
        if description_el is not None
        else ""
    )
    skills = [
        _clean_text(el.get_text(" ", strip=True))
        for el in soup.select('[data-qa="skills-element"]')
        if _clean_text(el.get_text(" ", strip=True))
    ]

    work_experience = _extract_detail_field_from_soup(soup, _DETAIL_FIELD_PREFIXES["work_experience"])
    employment_type = _extract_detail_field_from_soup(soup, _DETAIL_FIELD_PREFIXES["employment_type"])
    work_schedule = _extract_detail_field_from_soup(soup, _DETAIL_FIELD_PREFIXES["work_schedule"])
    working_hours = _extract_detail_field_from_soup(soup, _DETAIL_FIELD_PREFIXES["working_hours"])
    work_formats = _extract_detail_field_from_soup(soup, _DETAIL_FIELD_PREFIXES["work_formats"])
    compensation_frequency = _extract_detail_field_from_soup(
        soup, _DETAIL_FIELD_PREFIXES["compensation_frequency"]
    )
    salary = _clean_text(str(meta_parts.get("salary") or ""))
    location = _clean_text(str(meta_parts.get("location") or parsed_location))

    if not work_experience:
        work_experience = _clean_text(str(meta_parts.get("experience_name") or ""))
    if not employment_type:
        employment_type = _clean_text(str(meta_parts.get("employment_name") or ""))

    return {
        "description": description,
        "skills": skills,
        "title": parsed_title,
        "company_name": parsed_company,
        "company_url": _extract_company_link(soup),
        "salary": salary,
        "work_experience": work_experience,
        "employment_type": employment_type,
        "work_schedule": work_schedule,
        "work_formats": work_formats,
        "working_hours": working_hours,
        "compensation_frequency": compensation_frequency,
        "employer_data": {},
        "area_data": {},
        "orm_fields": {
            "snippet_requirement": None,
            "snippet_responsibility": None,
            "experience_id": None,
            "experience_name": work_experience or None,
            "schedule_id": None,
            "schedule_name": work_schedule or None,
            "employment_id": None,
            "employment_name": employment_type or None,
            "employment_form_id": None,
            "employment_form_name": None,
            "salary_from": None,
            "salary_to": None,
            "salary_currency": None,
            "salary_gross": None,
            "address_raw": location or None,
            "address_city": location or None,
            "address_street": None,
            "address_building": None,
            "address_lat": None,
            "address_lng": None,
            "metro_stations": None,
            "vacancy_type_id": None,
            "published_at": meta_parts.get("published_at"),
            "work_format": None,
            "professional_roles": None,
        },
    }


class HHScraper:
    def __init__(
        self,
        *,
        timeout: int = 15,
        retries: int = 3,
        page_delay: tuple[float, float] | None = None,
        vacancy_delay: tuple[float, float] | None = None,
        rate_limiter=None,
        public_api_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._timeout = timeout
        self._retries = retries
        if page_delay is None:
            self._page_delay = (
                settings.hh_public_api_list_delay_min_seconds,
                settings.hh_public_api_list_delay_max_seconds,
            )
        else:
            self._page_delay = page_delay
        if vacancy_delay is None:
            self._vacancy_delay = (
                settings.hh_public_api_vacancy_delay_min_seconds,
                settings.hh_public_api_vacancy_delay_max_seconds,
            )
        else:
            self._vacancy_delay = vacancy_delay
        self._rate_limiter = rate_limiter
        self._public_api_breaker_override = public_api_breaker

    def _hh_public_api_breaker(self) -> CircuitBreaker:
        if self._public_api_breaker_override is not None:
            return self._public_api_breaker_override
        return _get_hh_public_api_breaker()

    def _user_agent_for_request(self) -> str:
        return random.choice(_HH_BROWSER_USER_AGENTS + (settings.hh_user_agent,))

    async def _sleep_before_public_api_request(self, *, list_request: bool) -> None:
        lo, hi = self._page_delay if list_request else self._vacancy_delay
        if hi <= 0 and lo <= 0:
            return
        if hi < lo:
            lo, hi = hi, lo
        delay = random.uniform(lo, hi) if hi > lo else lo
        await asyncio.sleep(delay)

    def _headers(self) -> dict[str, str]:
        ua = self._user_agent_for_request()
        return {
            "User-Agent": ua,
            "HH-User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

    def _headers_api(self) -> dict[str, str]:
        ua = self._user_agent_for_request()
        return {
            "User-Agent": ua,
            "HH-User-Agent": ua,
            "Accept": "application/json",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

    async def _fetch_page(self, client: httpx.AsyncClient, url: str) -> BeautifulSoup | None:
        if self._rate_limiter is not None:
            await self._rate_limiter.acquire()
        for attempt in range(self._retries):
            try:
                resp = await client.get(url, headers=self._headers(), timeout=self._timeout)
                resp.raise_for_status()
                return BeautifulSoup(resp.text, "html.parser")
            except httpx.HTTPError as exc:
                if attempt < self._retries - 1:
                    wait = 3 + attempt * 2
                    logger.warning("Request error, retrying", error=str(exc), wait=wait)
                    await asyncio.sleep(wait)
                else:
                    logger.error("Failed to fetch page", url=url)
                    return None

    async def _fetch_page_with_meta(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> tuple[BeautifulSoup | None, str | None]:
        if self._rate_limiter is not None:
            await self._rate_limiter.acquire()
        for attempt in range(self._retries):
            try:
                resp = await client.get(url, headers=self._headers(), timeout=self._timeout)
                resp.raise_for_status()
                return BeautifulSoup(resp.text, "html.parser"), str(resp.url)
            except httpx.HTTPError as exc:
                if attempt < self._retries - 1:
                    wait = 3 + attempt * 2
                    logger.warning("Request error, retrying", error=str(exc), wait=wait)
                    await asyncio.sleep(wait)
                else:
                    logger.error("Failed to fetch page", url=url)
                    return None, None

    async def _fetch_api_page(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        storage_state: dict | None = None,
    ) -> tuple[dict | None, bool]:
        """Fetch JSON from HH API (single-vacancy detail).

        Returns (data, captcha_or_circuit_unresolved): second flag is True when the HTTP
        path indicated captcha or the breaker was open and browser JSON did not recover,
        so callers should raise after HTML Playwright also fails.
        """
        br = self._hh_public_api_breaker()
        if self._rate_limiter is not None:
            await self._rate_limiter.acquire()
        await self._sleep_before_public_api_request(list_request=False)

        cfg = HhUiApplyConfig.from_settings()
        circuit_open = not br.is_call_allowed()
        if circuit_open:
            logger.warning("hh_public_api_circuit_open_playwright_fallback", url=url)

        httpx_captcha = False
        rate_limit_round = 0
        rate_limit_http_exhausted = False
        if not circuit_open:
            for attempt in range(self._retries):
                try:
                    resp = await client.get(url, headers=self._headers_api(), timeout=self._timeout)
                    resp.raise_for_status()
                    br.record_success()
                    return resp.json(), False
                except httpx.HTTPStatusError as exc:
                    if exc.response is not None and exc.response.status_code == 404:
                        logger.info(
                            "HH API vacancy not found (404), not retrying",
                            url=url,
                        )
                        br.record_success()
                        return None, False
                    body = ""
                    status = exc.response.status_code if exc.response else None
                    if exc.response is not None:
                        body = exc.response.text[:_SEARCH_LIST_BODY_LOG_LEN]
                    if _hh_error_body_has_captcha(body):
                        logger.warning(
                            "HH API captcha required, trying Playwright JSON fallback",
                            url=url,
                            status=status,
                            body=body or None,
                        )
                        httpx_captcha = True
                        break
                    if _is_public_api_rate_limit_status(status) and not _hh_error_body_has_captcha(
                        body
                    ):
                        rate_limit_round += 1
                        max_rl = settings.hh_public_api_rate_limit_max_attempts_detail
                        if rate_limit_round >= max_rl:
                            rate_limit_http_exhausted = True
                            logger.warning(
                                "HH API detail rate-limit/forbidden HTTP retries exhausted",
                                url=url,
                                attempts=rate_limit_round,
                                status=status,
                            )
                            break
                        wait = min(
                            settings.hh_public_api_403_retry_base_seconds
                            * (2 ** (rate_limit_round - 1)),
                            settings.hh_public_api_403_retry_max_seconds,
                        )
                        logger.warning(
                            "HH API detail rate-limit/forbidden, exponential backoff",
                            url=url,
                            wait=wait,
                            attempt=rate_limit_round,
                            status=status,
                        )
                        await asyncio.sleep(wait)
                        continue
                    if attempt < self._retries - 1:
                        wait = 3 + attempt * 2
                        logger.warning(
                            "API request error, retrying",
                            error=str(exc),
                            wait=wait,
                            status=status,
                            body=body or None,
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.error(
                            "Failed to fetch API page",
                            url=url,
                            status=status,
                            body=body or None,
                        )
                except httpx.HTTPError as exc:
                    if attempt < self._retries - 1:
                        wait = 3 + attempt * 2
                        logger.warning("API request error, retrying", error=str(exc), wait=wait)
                        await asyncio.sleep(wait)
                    else:
                        logger.error("Failed to fetch API page", url=url)

        if rate_limit_http_exhausted:
            br.record_failure()

        pw_data = await asyncio.to_thread(
            fetch_public_hh_api_json_via_browser,
            storage_state=storage_state,
            config=cfg,
            api_url=url,
        )
        if pw_data and _hh_vacancy_detail_json_is_valid(pw_data):
            br.record_success()
            return pw_data, False
        return None, httpx_captcha or circuit_open

    async def _fetch_vacancy_search_page(
        self,
        client: httpx.AsyncClient,
        api_url: str,
        *,
        keyword: str,
        fallback_web_url: str | None = None,
        storage_state: dict | None = None,
    ) -> dict | None:
        """Fetch vacancy search (GET /vacancies). Retries then optional Playwright HTML search."""
        br = self._hh_public_api_breaker()
        if self._rate_limiter is not None:
            await self._rate_limiter.acquire()
        await self._sleep_before_public_api_request(list_request=True)

        circuit_open = not br.is_call_allowed()
        if circuit_open:
            logger.warning("hh_public_api_circuit_open_playwright_fallback", url=api_url)

        httpx_captcha = False
        rate_limit_round = 0
        rate_limit_http_exhausted = False
        if not circuit_open:
            for attempt in range(_SEARCH_LIST_MAX_ATTEMPTS):
                try:
                    resp = await client.get(
                        api_url,
                        headers=self._headers_api(),
                        timeout=self._timeout,
                    )
                    resp.raise_for_status()
                    br.record_success()
                    return resp.json()
                except httpx.HTTPStatusError as exc:
                    body = ""
                    status = exc.response.status_code if exc.response else None
                    if exc.response is not None:
                        body = exc.response.text[:_SEARCH_LIST_BODY_LOG_LEN]
                    if _hh_error_body_has_captcha(body):
                        logger.warning(
                            "Vacancy search captcha, trying Playwright search fallback",
                            url=api_url,
                            status=status,
                            body=body or None,
                        )
                        httpx_captcha = True
                        break
                    if _is_public_api_rate_limit_status(status) and not _hh_error_body_has_captcha(
                        body
                    ):
                        rate_limit_round += 1
                        max_rl = settings.hh_public_api_rate_limit_max_attempts_search
                        if rate_limit_round >= max_rl:
                            rate_limit_http_exhausted = True
                            logger.warning(
                                "Vacancy search rate-limit/forbidden HTTP retries exhausted",
                                url=api_url,
                                attempts=rate_limit_round,
                                status=status,
                            )
                            break
                        wait = min(
                            settings.hh_public_api_403_retry_base_seconds
                            * (2 ** (rate_limit_round - 1)),
                            settings.hh_public_api_403_retry_max_seconds,
                        )
                        logger.warning(
                            "Vacancy search rate-limit/forbidden, exponential backoff",
                            url=api_url,
                            wait=wait,
                            attempt=rate_limit_round,
                            status=status,
                        )
                        await asyncio.sleep(wait)
                        continue
                    wait = min(5 + attempt * 2, 60)
                    logger.warning(
                        "Vacancy search API error, retrying",
                        error=str(exc),
                        wait=wait,
                        attempt=attempt + 1,
                        max_attempts=_SEARCH_LIST_MAX_ATTEMPTS,
                        status=status,
                        body=body or None,
                        url=api_url,
                    )
                    if attempt >= _SEARCH_LIST_MAX_ATTEMPTS - 1:
                        logger.error(
                            "Vacancy search failed after retries",
                            url=api_url,
                            status=status,
                            body=body or None,
                        )
                        break
                    await asyncio.sleep(wait)
                except httpx.HTTPError as exc:
                    wait = min(5 + attempt * 2, 60)
                    logger.warning(
                        "Vacancy search request error, retrying",
                        error=str(exc),
                        wait=wait,
                        attempt=attempt + 1,
                        url=api_url,
                    )
                    if attempt >= _SEARCH_LIST_MAX_ATTEMPTS - 1:
                        logger.error("Vacancy search failed after retries", url=api_url)
                        break
                    await asyncio.sleep(wait)

        if rate_limit_http_exhausted:
            br.record_failure()

        if not fallback_web_url:
            if httpx_captcha:
                br.force_open()
                raise HHCaptchaRequiredError(
                    "HeadHunter requires captcha for vacancy search",
                    status_code=None,
                    body=None,
                )
            return None

        cfg = HhUiApplyConfig.from_settings()
        rendered = await asyncio.to_thread(
            render_search_page_with_storage,
            storage_state=storage_state,
            config=cfg,
            url=fallback_web_url,
        )
        if rendered.html is None:
            if httpx_captcha:
                br.force_open()
                raise HHCaptchaRequiredError(
                    "HeadHunter requires captcha for vacancy search",
                    status_code=None,
                    body=None,
                )
            return None
        if rendered.final_url and url_suggests_login_page(rendered.final_url):
            logger.warning(
                "Playwright vacancy search redirected to login",
                url=fallback_web_url,
                final_url=rendered.final_url,
            )
            if httpx_captcha:
                br.force_open()
                raise HHCaptchaRequiredError(
                    "HeadHunter requires captcha for vacancy search",
                    status_code=None,
                    body=None,
                )
            return None

        soup = BeautifulSoup(rendered.html, "html.parser")
        page_results = self._extract_vacancies_from_page(soup, keyword)
        raw_blocks = len(soup.select('[data-qa="vacancy-serp__vacancy"]'))
        if not page_results and raw_blocks == 0:
            if httpx_captcha:
                br.force_open()
                raise HHCaptchaRequiredError(
                    "HeadHunter requires captcha for vacancy search",
                    status_code=None,
                    body=None,
                )
            return None

        br.record_success()
        return _synthetic_search_api_payload_from_web_cards(page_results)

    async def fetch_vacancy_by_id(
        self,
        client: httpx.AsyncClient,
        vacancy_id: str,
        *,
        storage_state: dict | None = None,
    ) -> dict | None:
        """Fetch full vacancy detail from HH API (HTTP then Playwright JSON)."""
        url = _vacancy_api_url(vacancy_id)
        data, _ = await self._fetch_api_page(client, url, storage_state=storage_state)
        return data

    @staticmethod
    def _build_page_url(base_url: str, page: int) -> str:
        parsed = urlparse(base_url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        params["page"] = [str(page)]
        new_query = urlencode({k: v[0] for k, v in params.items()})
        return urlunparse(parsed._replace(query=new_query))

    @staticmethod
    def _build_api_url(base_url: str, page: int, per_page: int = 100) -> str:
        """Convert web search URL to HH.ru API URL, preserving filter params."""
        parsed = urlparse(base_url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        params["page"] = [str(page)]
        params["per_page"] = [str(per_page)]
        query_pairs: list[tuple[str, str]] = []
        for key, values in params.items():
            if key in _API_UNSUPPORTED_PARAMS:
                continue
            for val in values:
                query_pairs.append((key, val))
        new_query = urlencode(query_pairs)
        return urlunparse(
            parsed._replace(scheme="https", netloc="api.hh.ru", path="/vacancies", query=new_query)
        )

    @staticmethod
    def _extract_vacancy_id(url: str) -> str | None:
        match = HH_VACANCY_RE.search(url)
        return match.group(1) if match else None

    def _extract_vacancies_from_page(
        self,
        soup: BeautifulSoup,
        keyword: str,
    ) -> list[dict]:
        found: list[dict] = []
        blocks = soup.select('[data-qa="vacancy-serp__vacancy"]')

        logger.debug("Vacancy blocks on page", blocks_found=len(blocks))

        for block in blocks:
            link_el = None
            for a_tag in block.find_all("a", href=True):
                if HH_VACANCY_RE.match(a_tag["href"]):
                    link_el = a_tag
                    break
            if link_el is None:
                logger.debug("Vacancy block skipped — no matching link")
                continue

            href = link_el["href"]
            parsed = urlparse(href)
            clean_url = urlunparse(parsed._replace(query="", fragment=""))
            title = link_el.get_text(separator=" ", strip=True)

            keyword_matched = matches_keyword_expression(title, keyword)
            logger.debug(
                "Vacancy candidate",
                title=title,
                url=clean_url,
                keyword_matched=keyword_matched,
            )

            if keyword_matched:
                vacancy_id = self._extract_vacancy_id(clean_url)
                if vacancy_id:
                    item: dict = {
                        "url": clean_url,
                        "title": title,
                        "hh_vacancy_id": vacancy_id,
                    }
                    item.update(self._extract_card_metadata(block))
                    found.append(item)

        return found

    @staticmethod
    def _extract_card_metadata(block: Tag) -> dict:
        """Extract tags, company info, and salary from a search result card."""
        metadata: dict = {}

        tag_elements = block.select('[data-qa^="vacancy-serp__"]')
        tags = []
        for el in tag_elements:
            qa = el.get("data-qa", "")
            if qa and qa != "vacancy-serp__vacancy" and qa != "vacancy-serp__vacancy-employer":
                text = el.get_text(strip=True)
                if text:
                    tags.append(text)
        if tags:
            metadata["tags"] = tags

        employer_el = block.select_one('[data-qa="vacancy-serp__vacancy-employer"]')
        if employer_el:
            metadata["company_name"] = employer_el.get_text(strip=True)
            employer_link = employer_el.get("href") if employer_el.name == "a" else None
            if not employer_link:
                a_tag = employer_el.find("a", href=True)
                employer_link = a_tag["href"] if a_tag else None
            metadata["company_url"] = employer_link

        for el in block.find_all(class_=SALARY_CLASS_RE):
            raw = el.get_text(separator=" ", strip=True)
            text = _MULTI_SPACE_RE.sub(" ", raw)
            if text and _looks_like_salary(text):
                metadata["salary"] = text
                break

        return metadata

    def _extract_vacancies_from_api_response(self, data: dict, keyword: str) -> list[dict]:
        """Extract vacancy items from HH.ru API search response, applying keyword filter."""
        found: list[dict] = []
        items = data.get("items", [])

        logger.debug("API vacancy items on page", items_count=len(items))

        for item in items:
            name = item.get("name", "")
            alternate_url = item.get("alternate_url", "")
            vacancy_id = item.get("id")
            if not vacancy_id or not alternate_url:
                logger.debug("API item skipped — missing id or alternate_url")
                continue

            snippet = item.get("snippet") or {}
            snippet_text = " ".join(
                filter(None, [snippet.get("requirement"), snippet.get("responsibility")])
            )
            text_to_match = f"{name} {snippet_text}".strip()
            keyword_matched = matches_keyword_expression(text_to_match, keyword)
            logger.debug(
                "Vacancy candidate",
                title=name,
                url=alternate_url,
                keyword_matched=keyword_matched,
            )

            if not keyword_matched:
                continue

            parsed = urlparse(alternate_url)
            clean_url = urlunparse(parsed._replace(query="", fragment=""))

            result: dict = {
                "url": clean_url,
                "title": name,
                "hh_vacancy_id": str(vacancy_id),
            }

            employer = item.get("employer") or {}
            if employer.get("name"):
                result["company_name"] = employer["name"]
            if employer.get("alternate_url"):
                result["company_url"] = employer["alternate_url"]

            salary_str = _format_api_salary(item.get("salary"))
            if salary_str:
                result["salary"] = salary_str

            tags: list[str] = []
            for wf in item.get("work_format") or []:
                if isinstance(wf, dict) and wf.get("name"):
                    tags.append(wf["name"])
            schedule = item.get("schedule")
            if isinstance(schedule, dict) and schedule.get("name"):
                tags.append(schedule["name"])
            if tags:
                result["tags"] = tags

            found.append(result)

        return found

    @staticmethod
    def _collect_new_from_page(
        page_results: list[dict[str, str]],
        seen_urls: set[str],
        blacklisted: set[str],
        known_ids: set[str],
        collected: list[dict[str, str]],
        target_count: int,
    ) -> tuple[int, bool, int]:
        """Filter and append vacancies from a single page.

        Returns (new_count, page_had_unseen, blacklisted_skipped) where:
        - new_count: new (non-known) vacancies added to collected this page
        - page_had_unseen: page had vacancies not in seen_urls (loop-continuation signal)
        - blacklisted_skipped: unseen vacancies dropped because they are blacklisted

        Vacancies in known_ids are included in collected but not counted toward new_count.
        Vacancies in blacklisted are skipped entirely.
        """
        new_count = 0
        blacklisted_skipped = 0
        page_had_unseen = False
        for item in page_results:
            if item["url"] in seen_urls:
                continue
            seen_urls.add(item["url"])
            page_had_unseen = True
            vid = item["hh_vacancy_id"]
            if vid in blacklisted:
                blacklisted_skipped += 1
                continue
            collected.append(item)
            if vid not in known_ids:
                new_count += 1
                if new_count >= target_count:
                    break
        return new_count, page_had_unseen, blacklisted_skipped

    async def collect_vacancy_urls(
        self,
        base_url: str,
        keyword: str,
        target_count: int,
        *,
        blacklisted_ids: set[str] | None = None,
        known_ids_to_include: set[str] | None = None,
        parse_mode: str = "api",
        storage_state: dict | None = None,
    ) -> list[dict[str, str]]:
        """Collect vacancy URLs from search pages.

        Stops when target_count new (non-known) vacancies are collected, or pages
        are exhausted. Vacancies in known_ids_to_include are included in the
        result but do not count toward target_count (caller can mark them cached).
        Vacancies in blacklisted_ids are excluded entirely.
        """
        blacklisted = blacklisted_ids or set()
        known = known_ids_to_include or set()
        collected: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        new_collected_count = 0
        page = 0
        last_total_pages: int | None = None
        if parse_mode == "web":
            cfg = HhUiApplyConfig.from_settings()
            while new_collected_count < target_count:
                if page >= _MAX_PAGES:
                    logger.warning("Reached max page limit", limit=_MAX_PAGES, parse_mode=parse_mode)
                    break

                url = self._build_page_url(base_url, page)
                logger.info(
                    "Fetching search page",
                    url=url,
                    page=page + 1,
                    parse_mode=parse_mode,
                    has_cookies=bool(storage_state),
                )
                rendered = await asyncio.to_thread(
                    render_search_page_with_storage,
                    storage_state=storage_state,
                    config=cfg,
                    url=url,
                )
                if rendered.html is None:
                    logger.warning(
                        "Web vacancy search browser fetch failed",
                        page=page + 1,
                        url=url,
                        parse_mode=parse_mode,
                        has_cookies=bool(storage_state),
                        error=rendered.error,
                    )
                    break
                if rendered.final_url and url_suggests_login_page(rendered.final_url):
                    logger.warning(
                        "Web vacancy search redirected to login",
                        page=page + 1,
                        url=url,
                        final_url=rendered.final_url,
                        parse_mode=parse_mode,
                        has_cookies=bool(storage_state),
                    )
                    break
                soup = BeautifulSoup(rendered.html, "html.parser")
                page_results = self._extract_vacancies_from_page(soup, keyword)
                raw_blocks = len(soup.select('[data-qa="vacancy-serp__vacancy"]'))
                page_had_results = bool(page_results) or raw_blocks > 0

                if not page_had_results:
                    logger.info("No vacancy items on page", page=page + 1, url=url, parse_mode=parse_mode)
                    break

                new_count, _, blacklisted_skipped = self._collect_new_from_page(
                    page_results,
                    seen_urls,
                    blacklisted,
                    known,
                    collected,
                    target_count,
                )
                new_collected_count += new_count

                logger.info(
                    "Search page scraped",
                    page=page + 1,
                    url=url,
                    final_url=rendered.final_url,
                    parse_mode=parse_mode,
                    raw_blocks=raw_blocks,
                    cards_before_scroll=rendered.cards_before_scroll,
                    cards_after_scroll=rendered.cards_after_scroll,
                    keyword_matched=len(page_results),
                    blacklisted_skipped=blacklisted_skipped,
                    new=new_count,
                    total=len(collected),
                    target=target_count,
                    has_cookies=bool(storage_state),
                )
                page += 1
        else:
            async with httpx.AsyncClient() as client:
                while new_collected_count < target_count:
                    if page >= _MAX_PAGES:
                        logger.warning("Reached max page limit", limit=_MAX_PAGES, parse_mode=parse_mode)
                        break
                    if (
                        last_total_pages is not None
                        and last_total_pages > 0
                        and page >= last_total_pages
                    ):
                        break

                    api_url = self._build_api_url(base_url, page)
                    web_url = self._build_page_url(base_url, page)
                    logger.info(
                        "Fetching search page",
                        url=api_url,
                        page=page + 1,
                        parse_mode=parse_mode,
                    )
                    data = await self._fetch_vacancy_search_page(
                        client,
                        api_url,
                        keyword=keyword,
                        fallback_web_url=web_url,
                        storage_state=storage_state,
                    )
                    if data is None:
                        break

                    items = data.get("items", [])
                    if not items:
                        logger.info(
                            "No vacancy items on page",
                            page=page + 1,
                            url=api_url,
                            parse_mode=parse_mode,
                        )
                        break

                    last_total_pages = int(data.get("pages", 0) or 0)
                    page_results = self._extract_vacancies_from_api_response(data, keyword)
                    raw_blocks = len(items)
                    page_had_results = bool(items)

                    if not page_had_results:
                        logger.info(
                            "No vacancy items on page",
                            page=page + 1,
                            url=api_url,
                            parse_mode=parse_mode,
                        )
                        break

                    new_count, _, blacklisted_skipped = self._collect_new_from_page(
                        page_results,
                        seen_urls,
                        blacklisted,
                        known,
                        collected,
                        target_count,
                    )
                    new_collected_count += new_count

                    logger.info(
                        "Search page scraped",
                        page=page + 1,
                        url=api_url,
                        parse_mode=parse_mode,
                        raw_blocks=raw_blocks,
                        keyword_matched=len(page_results),
                        blacklisted_skipped=blacklisted_skipped,
                        new=new_count,
                        total=len(collected),
                        target=target_count,
                        has_cookies=bool(storage_state),
                    )

                    page += 1

        if not known:
            return collected[:target_count]
        return collected

    async def collect_vacancy_urls_batch(
        self,
        base_url: str,
        keyword: str,
        batch_size: int,
        *,
        start_page: int = 0,
        blacklisted_ids: set[str] | None = None,
        exclude_ids: set[str] | None = None,
        storage_state: dict | None = None,
    ) -> tuple[list[dict[str, str]], int, bool]:
        """Collect a batch of vacancy URLs for incremental fetching.

        Used when compatibility filter may reject many; caller fetches more batches
        until target count of passing vacancies is reached.

        Returns:
            (urls, next_page, has_more) where:
            - urls: up to batch_size new URLs (excluding blacklisted and exclude_ids)
            - next_page: page index to use for the next call
            - has_more: False when no more pages (exhausted or max pages)
        """
        skip_ids = (blacklisted_ids or set()) | (exclude_ids or set())
        collected: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        page = start_page
        last_total_pages: int | None = None

        async with httpx.AsyncClient() as client:
            while len(collected) < batch_size:
                if page >= _MAX_PAGES:
                    logger.warning("Reached max page limit", limit=_MAX_PAGES)
                    return collected[:batch_size], page, False

                if (
                    last_total_pages is not None
                    and last_total_pages > 0
                    and page >= last_total_pages
                ):
                    return collected[:batch_size], page, False

                api_url = self._build_api_url(base_url, page)
                web_url = self._build_page_url(base_url, page)
                logger.info("Fetching search page", url=api_url, page=page + 1)
                data = await self._fetch_vacancy_search_page(
                    client,
                    api_url,
                    keyword=keyword,
                    fallback_web_url=web_url,
                    storage_state=storage_state,
                )
                if data is None:
                    return collected[:batch_size], page, False

                items = data.get("items", [])
                if not items:
                    logger.info("No vacancy items on page", page=page + 1, url=api_url)
                    return collected[:batch_size], page, False

                last_total_pages = int(data.get("pages", 0) or 0)

                page_results = self._extract_vacancies_from_api_response(data, keyword)
                new_count, _, blacklisted_skipped = self._collect_new_from_page(
                    page_results,
                    seen_urls,
                    skip_ids,
                    set(),  # known_ids: batch API excludes all skip_ids, none are "known"
                    collected,
                    batch_size,
                )

                logger.info(
                    "Search page scraped",
                    page=page + 1,
                    url=api_url,
                    raw_blocks=len(items),
                    keyword_matched=len(page_results),
                    blacklisted_skipped=blacklisted_skipped,
                    new=new_count,
                    total=len(collected),
                    target=batch_size,
                )

                page += 1

        if last_total_pages and last_total_pages > 0:
            has_more = page < last_total_pages and page < _MAX_PAGES
        else:
            has_more = page < _MAX_PAGES
        return collected[:batch_size], page, has_more

    async def parse_vacancy_page(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        parse_mode: str = "api",
        storage_state: dict | None = None,
    ) -> dict:
        """Parse a single vacancy page. Returns page_data shape with structured fields.

        In ``api`` mode, fetches HH API detail JSON.
        In ``web`` mode, fetches the HTML vacancy page directly.
        Returns empty dict on failure.
        """
        if parse_mode == "web":
            soup, final_url = await self._fetch_page_with_meta(client, url)
            if soup is None:
                return {}
            if final_url and url_suggests_login_page(final_url):
                logger.warning("Web vacancy detail redirected to login", url=url, final_url=final_url)
                return {}
            return _map_html_vacancy_to_page_data(soup, url)

        vacancy_id = self._extract_vacancy_id(url)
        if not vacancy_id:
            return {}

        br = self._hh_public_api_breaker()
        api_url = _vacancy_api_url(vacancy_id)
        api_response, captcha_strike = await self._fetch_api_page(
            client,
            api_url,
            storage_state=storage_state,
        )
        if api_response:
            return _map_api_vacancy_to_page_data(api_response, {"url": url})

        cfg = HhUiApplyConfig.from_settings()
        rendered = await asyncio.to_thread(
            render_vacancy_detail_page_with_storage,
            storage_state=storage_state,
            config=cfg,
            url=url,
        )
        if rendered.html and rendered.final_url and not url_suggests_login_page(rendered.final_url):
            soup = BeautifulSoup(rendered.html, "html.parser")
            page_data = _map_html_vacancy_to_page_data(soup, url)
            if page_data.get("description") or page_data.get("title"):
                br.record_success()
                return page_data

        if captcha_strike:
            br.force_open()
            raise HHCaptchaRequiredError(
                "HeadHunter requires captcha for this request",
                status_code=None,
                body=None,
            )
        return {}
