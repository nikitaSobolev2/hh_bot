"""Unified HH parser service with global vacancy dedup and full vacancy parsing."""

import asyncio
from collections.abc import Awaitable, Callable

import httpx

from src.config import settings
from src.core.logging import get_logger
from src.services.hh_ui.applicant_http import httpx_cookies_from_storage_state
from src.schemas.vacancy import build_vacancy_api_context
from src.services.parser.scraper import HHCaptchaRequiredError, HHScraper

logger = get_logger(__name__)


def partition_collected_urls(
    collected_urls: list[dict],
    target_count: int,
    known_hh_ids: set[str],
) -> tuple[list[dict], list[dict]]:
    """Split search results into cached markers vs cards that need GET /vacancies/{id}."""
    cached_results: list[dict] = []
    to_fetch: list[dict] = []
    for vac in collected_urls:
        if vac["hh_vacancy_id"] in known_hh_ids:
            cached_results.append({"cached": True, "hh_vacancy_id": vac["hh_vacancy_id"], **vac})
        elif len(to_fetch) < target_count:
            to_fetch.append(vac)
    return cached_results, to_fetch


class HHParserService:
    """Wraps HHScraper with global dedup and full vacancy parsing."""

    def __init__(
        self,
        scraper: HHScraper | None = None,
        vacancy_fetch_concurrency: int | None = None,
        *,
        parse_mode: str = "api",
        storage_state: dict | None = None,
    ) -> None:
        self._scraper = scraper or HHScraper()
        self._vacancy_fetch_concurrency = (
            vacancy_fetch_concurrency
            if vacancy_fetch_concurrency is not None
            else settings.hh_vacancy_detail_concurrency
        )
        self._parse_mode = parse_mode
        self._storage_state = storage_state

    def build_client(self) -> httpx.AsyncClient:
        kwargs: dict = {}
        if self._parse_mode == "web" and self._storage_state:
            kwargs["cookies"] = httpx_cookies_from_storage_state(self._storage_state)
            kwargs["follow_redirects"] = True
        return httpx.AsyncClient(**kwargs)

    def merge_detail_into_card(self, vac: dict, page_data: dict) -> dict:
        """Merge HH API detail JSON (page_data) into search card ``vac``."""
        skills = page_data.get("skills", [])
        orm_fields = page_data.get("orm_fields", {})
        employer_data = page_data.get("employer_data", {})
        api_ctx = build_vacancy_api_context(orm_fields, employer_data, skills)
        merged = {
            **vac,
            **page_data,
            "raw_skills": skills,
            "vacancy_api_context": api_ctx,
        }
        merged.pop("skills", None)
        return merged

    async def fetch_detail_for_card(self, client: httpx.AsyncClient, vac: dict) -> dict | None:
        """GET /vacancies/{id} and merge into card; returns None on failed fetch."""
        page_data = await self._scraper.parse_vacancy_page(
            client,
            vac["url"],
            parse_mode=self._parse_mode,
        )
        if not page_data:
            return None
        return self.merge_detail_into_card(vac, page_data)

    async def fetch_details_batch_slice(
        self,
        client: httpx.AsyncClient,
        batch: list[dict],
        sem: asyncio.Semaphore,
    ) -> list:
        """Concurrent detail fetch for one slice; order matches ``batch``."""

        async def fetch_with_sem(vac: dict) -> dict | None:
            async with sem:
                return await self.fetch_detail_for_card(client, vac)

        return await asyncio.gather(*[fetch_with_sem(v) for v in batch], return_exceptions=True)

    async def parse_vacancies(
        self,
        search_url: str,
        keyword_filter: str,
        target_count: int,
        *,
        known_hh_ids: set[str] | None = None,
        on_vacancy_scraped: Callable[[int, int], Awaitable[None]] | None = None,
    ) -> list[dict]:
        """Scrape search pages and parse individual vacancy pages.

        Vacancies whose hh_vacancy_id is in *known_hh_ids* are not fetched
        individually but returned with ``cached=True`` so callers can clone
        from the database instead.  Scraping stops once *target_count* **new**
        vacancies have been fully parsed or all search pages are exhausted.
        """
        known = known_hh_ids or set()
        collected_urls = await self._scraper.collect_vacancy_urls(
            search_url,
            keyword_filter,
            target_count,
            known_ids_to_include=known,
            parse_mode=self._parse_mode,
            storage_state=self._storage_state,
        )

        cached_results, to_fetch = partition_collected_urls(collected_urls, target_count, known)
        results: list[dict] = list(cached_results)

        sem = asyncio.Semaphore(self._vacancy_fetch_concurrency)
        new_count = 0
        async with self.build_client() as client:
            for batch_start in range(0, len(to_fetch), self._vacancy_fetch_concurrency):
                batch = to_fetch[batch_start : batch_start + self._vacancy_fetch_concurrency]
                batch_results = await self.fetch_details_batch_slice(client, batch, sem)
                for i, r in enumerate(batch_results):
                    if isinstance(r, HHCaptchaRequiredError):
                        raise r
                    if isinstance(r, Exception):
                        logger.warning("Vacancy fetch failed", vacancy=batch[i], error=r)
                        continue
                    if r is not None:
                        results.append(r)
                        new_count += 1
                        if on_vacancy_scraped:
                            await on_vacancy_scraped(new_count, target_count)
                    if new_count >= target_count:
                        break
                if new_count >= target_count:
                    break

        logger.info(
            "HHParserService finished",
            total=len(results),
            new=new_count,
            cached=len(results) - new_count,
            parse_mode=self._parse_mode,
        )
        return results
