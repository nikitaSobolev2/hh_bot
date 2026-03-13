"""Orchestrates the keyword extraction pipeline for a parsing company."""

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable

import httpx

from src.core.logging import get_logger
from src.schemas.vacancy import PipelineResult, VacancyData
from src.services.ai.client import AIClient
from src.services.parser.scraper import HHScraper

logger = get_logger(__name__)

OnProgressCallback = Callable[[int, int], Awaitable[None]]
CompatFilterFn = Callable[[VacancyData], Awaitable[bool]]

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
        compat_filter: CompatFilterFn | None = None,
        concurrency: int = _DEFAULT_CONCURRENCY,
        ai_concurrency: int = _AI_CONCURRENCY,
        resume_from: tuple[list[dict], int] | None = None,
    ) -> PipelineResult:
        """Run the parsing pipeline.

        When resume_from is provided as (urls, skip_count), use the given URLs
        and skip the first skip_count (already processed). No scraping is done.
        """
        if resume_from is not None:
            vacancies, skip_count = resume_from
        else:
            vacancies = await self._scraper.collect_vacancy_urls(
                search_url,
                keyword_filter,
                target_count,
                blacklisted_ids=blacklisted_ids,
            )
            skip_count = 0

        if not vacancies:
            logger.warning("No vacancies found")
            return PipelineResult(vacancies=[], keywords=[], skills=[])

        total = len(vacancies)
        vacancies_to_process = vacancies[skip_count:]
        sem = asyncio.Semaphore(concurrency)
        ai_sem = asyncio.Semaphore(ai_concurrency)

        scrape_lock = asyncio.Lock()
        scraped_count = [skip_count]
        kw_lock = asyncio.Lock()
        kw_count = [skip_count]

        if skip_count > 0 and on_page_scraped:
            await on_page_scraped(total, total)

        async def _process_vacancy(
            client: httpx.AsyncClient,
            vac: dict,
        ) -> tuple[VacancyData, list[str], list[str]] | None:
            async with sem:
                page_data = await self._scraper.parse_vacancy_page(client, vac["url"])

                description = page_data.get("description", "")
                skills: list[str] = page_data.get("skills", [])

                async with scrape_lock:
                    scraped_count[0] += 1
                    scrape_current = scraped_count[0]

                if on_page_scraped:
                    await on_page_scraped(scrape_current, total)

                partial = VacancyData(
                    hh_vacancy_id=vac["hh_vacancy_id"],
                    url=vac["url"],
                    title=vac["title"],
                    raw_skills=skills,
                    description=description,
                    salary=vac.get("salary", ""),
                    company_name=vac.get("company_name", ""),
                    work_experience=page_data.get("work_experience", ""),
                    employment_type=page_data.get("employment_type", ""),
                    work_schedule=page_data.get("work_schedule", ""),
                    work_formats=page_data.get("work_formats", ""),
                    compensation_frequency=page_data.get("compensation_frequency", ""),
                    working_hours=page_data.get("working_hours", ""),
                )

                if compat_filter is not None:
                    async with ai_sem:
                        passes = await compat_filter(partial)
                    if not passes:
                        async with kw_lock:
                            kw_count[0] += 1
                            current = kw_count[0]
                        logger.info(
                            "Vacancy skipped (compat filter)",
                            index=current,
                            total=total,
                            title=vac["title"][:60],
                        )
                        if on_vacancy_processed:
                            await on_vacancy_processed(current, total)
                        return None

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

                vacancy_data = VacancyData(
                    hh_vacancy_id=partial.hh_vacancy_id,
                    url=partial.url,
                    title=partial.title,
                    raw_skills=partial.raw_skills,
                    description=partial.description,
                    ai_keywords=ai_keywords,
                    salary=partial.salary,
                    company_name=partial.company_name,
                    work_experience=partial.work_experience,
                    employment_type=partial.employment_type,
                    work_schedule=partial.work_schedule,
                    work_formats=partial.work_formats,
                    compensation_frequency=partial.compensation_frequency,
                    working_hours=partial.working_hours,
                )
                return vacancy_data, skills, ai_keywords

        async with httpx.AsyncClient() as client:
            raw_results = await asyncio.gather(
                *[_process_vacancy(client, vac) for vac in vacancies_to_process]
            )

        keywords_counter: Counter[str] = Counter()
        skills_counter: Counter[str] = Counter()
        processed_vacancies: list[VacancyData] = []

        for result_item in raw_results:
            if result_item is None:
                continue
            vacancy_data, skills, ai_keywords = result_item
            processed_vacancies.append(vacancy_data)
            for skill in skills:
                skills_counter[skill.strip()] += 1
            for kw in ai_keywords:
                keywords_counter[kw.strip()] += 1

        return PipelineResult(
            vacancies=processed_vacancies,
            keywords=keywords_counter.most_common(),
            skills=skills_counter.most_common(),
        )
