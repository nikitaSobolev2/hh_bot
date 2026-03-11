"""Async HH.ru vacancy scraper.

Replaces synchronous requests-based scraping from the original script
with httpx async client, configurable delays, and blacklist support.
"""

import asyncio
import random
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

from src.core.logging import get_logger
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


class HHScraper:
    def __init__(
        self,
        *,
        timeout: int = 15,
        retries: int = 3,
        page_delay: tuple[float, float] = (1.0, 2.0),
        vacancy_delay: tuple[float, float] = (1.0, 2.5),
    ) -> None:
        self._ua = UserAgent()
        self._timeout = timeout
        self._retries = retries
        self._page_delay = page_delay
        self._vacancy_delay = vacancy_delay

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._ua.random,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

    async def _fetch_page(self, client: httpx.AsyncClient, url: str) -> BeautifulSoup | None:
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

    @staticmethod
    def _build_page_url(base_url: str, page: int) -> str:
        parsed = urlparse(base_url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        params["page"] = [str(page)]
        new_query = urlencode({k: v[0] for k, v in params.items()})
        return urlunparse(parsed._replace(query=new_query))

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

    @staticmethod
    def _collect_new_from_page(
        page_results: list[dict[str, str]],
        seen_urls: set[str],
        blacklisted: set[str],
        collected: list[dict[str, str]],
        target_count: int,
    ) -> tuple[int, bool, int]:
        """Filter and append new vacancies from a single page.

        Returns (new_count, page_had_unseen, blacklisted_skipped) where:
        - new_count: vacancies added to collected this page
        - page_had_unseen: page had vacancies not in seen_urls (loop-continuation signal)
        - blacklisted_skipped: unseen vacancies dropped because they are blacklisted
        """
        new_count = 0
        blacklisted_skipped = 0
        page_had_unseen = False
        for item in page_results:
            if item["url"] in seen_urls:
                continue
            seen_urls.add(item["url"])
            page_had_unseen = True
            if item["hh_vacancy_id"] in blacklisted:
                blacklisted_skipped += 1
                continue
            collected.append(item)
            new_count += 1
            if len(collected) >= target_count:
                break
        return new_count, page_had_unseen, blacklisted_skipped

    async def collect_vacancy_urls(
        self,
        base_url: str,
        keyword: str,
        target_count: int,
        *,
        blacklisted_ids: set[str] | None = None,
    ) -> list[dict[str, str]]:
        blacklisted = blacklisted_ids or set()
        collected: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        page = 0
        zero_pages = 0

        async with httpx.AsyncClient() as client:
            while len(collected) < target_count:
                url = self._build_page_url(base_url, page)
                logger.info("Fetching search page", url=url, page=page + 1)
                soup = await self._fetch_page(client, url)
                if soup is None:
                    break

                raw_blocks = soup.select('[data-qa="vacancy-serp__vacancy"]')
                if not raw_blocks:
                    logger.info("No vacancy blocks on page", page=page + 1, url=url)
                    break

                page_results = self._extract_vacancies_from_page(soup, keyword)
                new_count, page_had_unseen, blacklisted_skipped = self._collect_new_from_page(
                    page_results,
                    seen_urls,
                    blacklisted,
                    collected,
                    target_count,
                )

                zero_pages = zero_pages + 1 if not page_had_unseen else 0
                logger.info(
                    "Search page scraped",
                    page=page + 1,
                    url=url,
                    raw_blocks=len(raw_blocks),
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
                await asyncio.sleep(random.uniform(*self._page_delay))

        return collected[:target_count]

    _VACANCY_DETAIL_SELECTORS: dict[str, str] = {
        "compensation_frequency": "compensation-frequency-text",
        "work_experience": "work-experience-text",
        "employment_type": "common-employment-text",
        "work_schedule": "work-schedule-by-days-text",
        "working_hours": "working-hours-text",
        "work_formats": "work-formats-text",
    }

    async def parse_vacancy_page(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> dict:
        """Parse a single vacancy page and return all available fields.

        Returns a dict with keys: description, skills, and optional detail
        fields (compensation_frequency, work_experience, etc.).
        Returns an empty dict on fetch failure.
        """
        soup = await self._fetch_page(client, url)
        if soup is None:
            return {}

        title_el = soup.find(attrs={"data-qa": "vacancy-title"})
        title = title_el.get_text(strip=True) if title_el else ""

        desc_el = soup.find(attrs={"data-qa": "vacancy-description"})
        description = desc_el.get_text(separator="\n", strip=True) if desc_el else ""

        company_el = soup.find(attrs={"data-qa": "vacancy-company-name"})
        company_name = company_el.get_text(strip=True) if company_el else ""

        skill_elements = soup.select('[data-qa="skills-element"] > div')
        skills = [el.get_text(strip=True) for el in skill_elements if el.get_text(strip=True)]

        result: dict = {"description": description, "skills": skills, "title": title, "company_name": company_name}

        for field, data_qa in self._VACANCY_DETAIL_SELECTORS.items():
            el = soup.find(attrs={"data-qa": data_qa})
            if el:
                result[field] = _strip_field_prefix(field, el.get_text(strip=True))

        return result
