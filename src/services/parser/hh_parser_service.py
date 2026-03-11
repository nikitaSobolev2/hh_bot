"""Unified HH parser service with global vacancy deduplication."""

import asyncio
import random
from collections.abc import Awaitable, Callable

import httpx

from src.core.logging import get_logger
from src.services.parser.scraper import HHScraper

logger = get_logger(__name__)


class HHParserService:
    """Wraps HHScraper with global dedup and full vacancy parsing."""

    def __init__(self, scraper: HHScraper | None = None) -> None:
        self._scraper = scraper or HHScraper()

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
            target_count + len(known),
            blacklisted_ids=set(),
        )

        results: list[dict] = []
        new_count = 0

        async with httpx.AsyncClient() as client:
            for vac in collected_urls:
                hh_id = vac["hh_vacancy_id"]

                if hh_id in known:
                    results.append({"cached": True, "hh_vacancy_id": hh_id, **vac})
                    continue

                if new_count >= target_count:
                    break

                page_data = await self._scraper.parse_vacancy_page(client, vac["url"])
                if not page_data:
                    continue

                merged = {**vac, **page_data, "raw_skills": page_data.get("skills", [])}
                merged.pop("skills", None)
                results.append(merged)
                new_count += 1
                if on_vacancy_scraped:
                    await on_vacancy_scraped(new_count, target_count)

                await asyncio.sleep(random.uniform(*self._scraper._vacancy_delay))

        logger.info(
            "HHParserService finished",
            total=len(results),
            new=new_count,
            cached=len(results) - new_count,
        )
        return results
