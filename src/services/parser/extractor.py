"""Orchestrates the keyword extraction pipeline for a parsing company."""

import asyncio
import random
from collections import Counter
from collections.abc import Awaitable, Callable

import httpx

from src.core.logging import get_logger
from src.services.ai.client import AIClient
from src.services.parser.scraper import HHScraper

logger = get_logger(__name__)

OnVacancyProcessed = Callable[[int, int], Awaitable[None]]


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
        on_vacancy_processed: OnVacancyProcessed | None = None,
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

        keywords_counter: Counter = Counter()
        skills_counter: Counter = Counter()
        processed_vacancies: list[dict] = []

        async with httpx.AsyncClient() as client:
            for idx, vac in enumerate(vacancies, 1):
                description, skills = await self._scraper.parse_vacancy_page(
                    client,
                    vac["url"],
                )

                for skill in skills:
                    skills_counter[skill.strip()] += 1

                ai_keywords: list[str] = []
                if description:
                    ai_keywords = await self._ai.extract_keywords(description)
                    for kw in ai_keywords:
                        keywords_counter[kw.strip()] += 1

                processed_vacancies.append(
                    {
                        **vac,
                        "description": description,
                        "raw_skills": skills,
                        "ai_keywords": ai_keywords,
                    }
                )

                logger.info(
                    "Vacancy processed",
                    index=idx,
                    total=len(vacancies),
                    title=vac["title"][:60],
                    keywords_found=len(ai_keywords),
                    skills_found=len(skills),
                )

                if on_vacancy_processed:
                    await on_vacancy_processed(idx, len(vacancies))

                await asyncio.sleep(random.uniform(1.0, 2.5))

        return {
            "vacancies": processed_vacancies,
            "keywords": dict(keywords_counter.most_common()),
            "skills": dict(skills_counter.most_common()),
        }
