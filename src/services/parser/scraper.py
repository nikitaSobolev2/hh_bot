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
    ) -> list[dict[str, str]]:
        found: list[dict[str, str]] = []
        blocks = soup.select('[data-qa="vacancy-serp__vacancy"]')

        for block in blocks:
            link_el = None
            for a_tag in block.find_all("a", href=True):
                if HH_VACANCY_RE.match(a_tag["href"]):
                    link_el = a_tag
                    break
            if link_el is None:
                continue

            href = link_el["href"]
            parsed = urlparse(href)
            clean_url = urlunparse(parsed._replace(query="", fragment=""))
            title = link_el.get_text(separator=" ", strip=True)

            if matches_keyword_expression(title, keyword):
                vacancy_id = self._extract_vacancy_id(clean_url)
                if vacancy_id:
                    found.append(
                        {
                            "url": clean_url,
                            "title": title,
                            "hh_vacancy_id": vacancy_id,
                        }
                    )

        return found

    @staticmethod
    def _collect_new_from_page(
        page_results: list[dict[str, str]],
        seen_urls: set[str],
        blacklisted: set[str],
        collected: list[dict[str, str]],
        target_count: int,
    ) -> int:
        """Filter and append new vacancies from a single page."""
        new_count = 0
        for item in page_results:
            if item["url"] in seen_urls:
                continue
            if item["hh_vacancy_id"] in blacklisted:
                continue
            seen_urls.add(item["url"])
            collected.append(item)
            new_count += 1
            if len(collected) >= target_count:
                break
        return new_count

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
                soup = await self._fetch_page(client, url)
                if soup is None:
                    break

                if not soup.select('[data-qa="vacancy-serp__vacancy"]'):
                    logger.info("No vacancy blocks on page", page=page + 1)
                    break

                page_results = self._extract_vacancies_from_page(soup, keyword)
                new_count = self._collect_new_from_page(
                    page_results,
                    seen_urls,
                    blacklisted,
                    collected,
                    target_count,
                )

                zero_pages = zero_pages + 1 if new_count == 0 else 0
                logger.info(
                    "Search page scraped",
                    page=page + 1,
                    new=new_count,
                    total=len(collected),
                    target=target_count,
                )

                if zero_pages >= 2:
                    logger.warning("2 pages with no new vacancies — stopping")
                    break

                page += 1
                await asyncio.sleep(random.uniform(*self._page_delay))

        return collected[:target_count]

    async def parse_vacancy_page(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> tuple[str, list[str]]:
        soup = await self._fetch_page(client, url)
        if soup is None:
            return "", []

        desc_el = soup.find(attrs={"data-qa": "vacancy-description"})
        description = desc_el.get_text(separator="\n", strip=True) if desc_el else ""

        skill_elements = soup.select('[data-qa="skills-element"] > div')
        skills = [el.get_text(strip=True) for el in skill_elements if el.get_text(strip=True)]

        return description, skills
