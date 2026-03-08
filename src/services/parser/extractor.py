"""Orchestrates the keyword extraction pipeline for a parsing company."""

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable

import httpx

from src.core.logging import get_logger
from src.services.ai.client import AIClient
from src.services.parser.scraper import HHScraper

logger = get_logger(__name__)

OnProgressCallback = Callable[[int, int], Awaitable[None]]

_DEFAULT_CONCURRENCY = 15
_AI_CONCURRENCY = 3


class ParsingExtractor:
    """Runs the full parsing + AI extraction pipeline."""

    def __init__(
        self,
        scraper: HHScraper | None = None,
        ai_client: AIClient | None = None,
    ) -> None:
        self._scraper = scraper or HHScraper()
        self._ai = ai_client or AIClient()

    async def run_pipeline(
        self,
        search_url: str,
        keyword_filter: str,
        target_count: int,
        *,
        blacklisted_ids: set[str] | None = None,
        on_page_scraped: OnProgressCallback | None = None,
        on_vacancy_processed: OnProgressCallback | None = None,
        concurrency: int = _DEFAULT_CONCURRENCY,
        ai_concurrency: int = _AI_CONCURRENCY,
    ) -> dict:
        vacancies = await self._scraper.collect_vacancy_urls(
            search_url,
            keyword_filter,
            target_count,
            blacklisted_ids=blacklisted_ids,
        )

        if not vacancies:
            logger.warning("No vacancies found")
            return {"vacancies": [], "keywords": {}, "skills": {}}

        total = len(vacancies)
        sem = asyncio.Semaphore(concurrency)
        ai_sem = asyncio.Semaphore(ai_concurrency)

        scrape_lock = asyncio.Lock()
        scraped_count = [0]
        kw_lock = asyncio.Lock()
        kw_count = [0]

        async def _process_vacancy(
            client: httpx.AsyncClient,
            vac: dict,
        ) -> tuple[dict, list[str], list[str]]:
            async with sem:
                description, skills = await self._scraper.parse_vacancy_page(
                    client,
                    vac["url"],
                )

                async with scrape_lock:
                    scraped_count[0] += 1
                    scrape_current = scraped_count[0]

                if on_page_scraped:
                    await on_page_scraped(scrape_current, total)

                ai_keywords: list[str] = []
                if description:
                    async with ai_sem:
                        ai_keywords = await self._ai.extract_keywords(description)

                async with kw_lock:
                    kw_count[0] += 1
                    current = kw_count[0]

                logger.info(
                    "Vacancy processed",
                    index=current,
                    total=total,
                    title=vac["title"][:60],
                    keywords_found=len(ai_keywords),
                    skills_found=len(skills),
                )

                if on_vacancy_processed:
                    await on_vacancy_processed(current, total)

                return (
                    {
                        **vac,
                        "description": description,
                        "raw_skills": skills,
                        "ai_keywords": ai_keywords,
                    },
                    skills,
                    ai_keywords,
                )

        async with httpx.AsyncClient() as client:
            results = await asyncio.gather(*[_process_vacancy(client, vac) for vac in vacancies])

        keywords_counter: Counter = Counter()
        skills_counter: Counter = Counter()
        processed_vacancies: list[dict] = []

        for vac_dict, skills, ai_keywords in results:
            processed_vacancies.append(vac_dict)
            for skill in skills:
                skills_counter[skill.strip()] += 1
            for kw in ai_keywords:
                keywords_counter[kw.strip()] += 1

        return {
            "vacancies": processed_vacancies,
            "keywords": dict(keywords_counter.most_common()),
            "skills": dict(skills_counter.most_common()),
        }
