"""Unified HH parser service with global vacancy deduplication."""

import asyncio
from collections.abc import Awaitable, Callable

import httpx

from src.config import settings
from src.core.logging import get_logger
from src.schemas.vacancy import build_vacancy_api_context
from src.services.parser.scraper import HHScraper

logger = get_logger(__name__)


class HHParserService:
    """Wraps HHScraper with global dedup and full vacancy parsing."""

    def __init__(
        self,
        scraper: HHScraper | None = None,
        vacancy_fetch_concurrency: int | None = None,
    ) -> None:
        self._scraper = scraper or HHScraper()
        self._vacancy_fetch_concurrency = (
            vacancy_fetch_concurrency
            if vacancy_fetch_concurrency is not None
            else settings.hh_vacancy_detail_concurrency
        )

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
        )

        results: list[dict] = []
        to_fetch: list[dict] = []

        for vac in collected_urls:
            if vac["hh_vacancy_id"] in known:
                results.append({"cached": True, "hh_vacancy_id": vac["hh_vacancy_id"], **vac})
            elif len(to_fetch) < target_count:
                to_fetch.append(vac)

        async def fetch_one(vac: dict) -> dict | None:
            page_data = await self._scraper.parse_vacancy_page(client, vac["url"])
            if not page_data:
                return None
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

        sem = asyncio.Semaphore(self._vacancy_fetch_concurrency)

        async def fetch_with_sem(vac: dict) -> dict | None:
            async with sem:
                return await fetch_one(vac)

        new_count = 0
        async with httpx.AsyncClient() as client:
            for batch_start in range(0, len(to_fetch), self._vacancy_fetch_concurrency):
                batch = to_fetch[batch_start : batch_start + self._vacancy_fetch_concurrency]
                batch_results = await asyncio.gather(
                    *[fetch_with_sem(v) for v in batch],
                    return_exceptions=True,
                )
                for i, r in enumerate(batch_results):
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
        )
        return results
