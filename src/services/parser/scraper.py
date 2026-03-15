"""Async HH.ru vacancy scraper.

Replaces synchronous requests-based scraping from the original script
with httpx async client, configurable delays, and blacklist support.
"""

import asyncio
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

from src.core.logging import get_logger
from src.services.parser.hh_mapper import map_api_vacancy_to_orm_fields
from src.services.parser.keyword_match import matches_keyword_expression

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
_MAX_PAGES = 100  # ~2000 vacancies max; API supports up to 100 per page
HH_API_BASE = "https://api.hh.ru/vacancies"
_API_UNSUPPORTED_PARAMS = frozenset(
    {"hhtmFrom", "hhtmFromLabel", "L_save_area", "ored_clusters", "enable_snippets", "search_field"}
)


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


class HHScraper:
    def __init__(
        self,
        *,
        timeout: int = 15,
        retries: int = 3,
        page_delay: tuple[float, float] = (0.0, 0.0),
        vacancy_delay: tuple[float, float] = (0.0, 0.0),
        rate_limiter=None,
    ) -> None:
        self._ua = UserAgent()
        self._timeout = timeout
        self._retries = retries
        self._page_delay = page_delay
        self._vacancy_delay = vacancy_delay
        self._rate_limiter = rate_limiter

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._ua.random,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

    def _headers_api(self) -> dict[str, str]:
        return {
            "User-Agent": self._ua.random,
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

    async def _fetch_api_page(self, client: httpx.AsyncClient, url: str) -> dict | None:
        """Fetch vacancy search page from HH.ru API. Returns parsed JSON or None on failure."""
        if self._rate_limiter is not None:
            await self._rate_limiter.acquire()
        for attempt in range(self._retries):
            try:
                resp = await client.get(url, headers=self._headers_api(), timeout=self._timeout)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPError as exc:
                if attempt < self._retries - 1:
                    wait = 3 + attempt * 2
                    logger.warning("API request error, retrying", error=str(exc), wait=wait)
                    await asyncio.sleep(wait)
                else:
                    logger.error("Failed to fetch API page", url=url)
                    return None

    async def fetch_vacancy_by_id(
        self,
        client: httpx.AsyncClient,
        vacancy_id: str,
    ) -> dict | None:
        """Fetch full vacancy detail from HH API. Returns raw JSON or None on failure."""
        url = _vacancy_api_url(vacancy_id)
        return await self._fetch_api_page(client, url)

    @staticmethod
    def _build_page_url(base_url: str, page: int) -> str:
        parsed = urlparse(base_url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        params["page"] = [str(page)]
        new_query = urlencode({k: v[0] for k, v in params.items()})
        return urlunparse(parsed._replace(query=new_query))

    @staticmethod
    def _build_api_url(base_url: str, page: int, per_page: int = 50) -> str:
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
    def _extract_card_metadata(block: "Tag") -> dict:  # noqa: F821
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

            keyword_matched = matches_keyword_expression(name, keyword)
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
        zero_pages = 0

        async with httpx.AsyncClient() as client:
            while new_collected_count < target_count:
                if page >= _MAX_PAGES:
                    logger.warning("Reached max page limit", limit=_MAX_PAGES)
                    break
                url = self._build_api_url(base_url, page)
                logger.info("Fetching search page", url=url, page=page + 1)
                data = await self._fetch_api_page(client, url)
                if data is None:
                    break

                items = data.get("items", [])
                if not items:
                    logger.info("No vacancy items on page", page=page + 1, url=url)
                    break

                total_pages = data.get("pages", 0)
                if page >= total_pages:
                    break

                page_results = self._extract_vacancies_from_api_response(data, keyword)
                new_count, _, blacklisted_skipped = self._collect_new_from_page(
                    page_results,
                    seen_urls,
                    blacklisted,
                    known,
                    collected,
                    target_count,
                )
                new_collected_count += new_count

                zero_pages = zero_pages + 1 if new_count == 0 else 0
                logger.info(
                    "Search page scraped",
                    page=page + 1,
                    url=url,
                    raw_blocks=len(items),
                    keyword_matched=len(page_results),
                    blacklisted_skipped=blacklisted_skipped,
                    new=new_count,
                    total=len(collected),
                    target=target_count,
                )

                if zero_pages >= 3:
                    logger.warning("3 pages with no new vacancies — stopping")
                    break

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
    ) -> tuple[list[dict[str, str]], int, bool]:
        """Collect a batch of vacancy URLs for incremental fetching.

        Used when compatibility filter may reject many; caller fetches more batches
        until target count of passing vacancies is reached.

        Returns:
            (urls, next_page, has_more) where:
            - urls: up to batch_size new URLs (excluding blacklisted and exclude_ids)
            - next_page: page index to use for the next call
            - has_more: False when no more pages (exhausted, max pages, or 3 empty)
        """
        skip_ids = (blacklisted_ids or set()) | (exclude_ids or set())
        collected: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        page = start_page
        zero_pages = 0

        async with httpx.AsyncClient() as client:
            while len(collected) < batch_size:
                if page >= _MAX_PAGES:
                    logger.warning("Reached max page limit", limit=_MAX_PAGES)
                    return collected[:batch_size], page, False

                url = self._build_api_url(base_url, page)
                logger.info("Fetching search page", url=url, page=page + 1)
                data = await self._fetch_api_page(client, url)
                if data is None:
                    return collected[:batch_size], page, False

                items = data.get("items", [])
                if not items:
                    logger.info("No vacancy items on page", page=page + 1, url=url)
                    return collected[:batch_size], page, False

                total_pages = data.get("pages", 0)
                if page >= total_pages:
                    return collected[:batch_size], page + 1, False

                page_results = self._extract_vacancies_from_api_response(data, keyword)
                new_count, _, blacklisted_skipped = self._collect_new_from_page(
                    page_results,
                    seen_urls,
                    skip_ids,
                    set(),  # known_ids: batch API excludes all skip_ids, none are "known"
                    collected,
                    batch_size,
                )

                zero_pages = zero_pages + 1 if new_count == 0 else 0
                logger.info(
                    "Search page scraped",
                    page=page + 1,
                    url=url,
                    raw_blocks=len(items),
                    keyword_matched=len(page_results),
                    blacklisted_skipped=blacklisted_skipped,
                    new=new_count,
                    total=len(collected),
                    target=batch_size,
                )

                if zero_pages >= 3:
                    logger.warning("3 pages with no new vacancies — stopping")
                    return collected[:batch_size], page + 1, False

                page += 1

        has_more = page < _MAX_PAGES and zero_pages < 3
        return collected[:batch_size], page, has_more

    async def parse_vacancy_page(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> dict:
        """Parse a single vacancy page via HH API. Returns page_data shape with structured fields.

        For HH.ru URLs, fetches from API and maps to page_data
        (employer_data, area_data, orm_fields).
        Returns empty dict on failure.
        """
        vacancy_id = self._extract_vacancy_id(url)
        if not vacancy_id:
            return {}

        api_response = await self.fetch_vacancy_by_id(client, vacancy_id)
        if not api_response:
            return {}

        return _map_api_vacancy_to_page_data(api_response, {"url": url})
