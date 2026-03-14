"""Orchestrates the keyword extraction pipeline for a parsing company."""

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable

import httpx

from src.core.logging import get_logger
from src.schemas.vacancy import PipelineResult, VacancyData
from src.services.ai.client import AIClient
from src.services.ai.prompts import VacancyCompatInput
from src.services.parser.scraper import HHScraper

logger = get_logger(__name__)

OnProgressCallback = Callable[[int, int, VacancyData | None], Awaitable[None]]

# (tech_stack, work_exp_text, threshold) — when set, use batch compat instead of per-vacancy
CompatParams = tuple[list[str], str, int]

_DEFAULT_CONCURRENCY = 15
_AI_CONCURRENCY = 3
_COMPAT_BATCH_SIZE = 8


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
        compat_params: CompatParams | None = None,
        concurrency: int = _DEFAULT_CONCURRENCY,
        ai_concurrency: int = _AI_CONCURRENCY,
        resume_from: tuple[list[dict], int] | None = None,
    ) -> PipelineResult:
        """Run the parsing pipeline.

        When resume_from is provided as (urls, skip_count), use the given URLs
        and skip the first skip_count (already processed). No scraping is done.

        When compat_params (tech_stack, work_exp, threshold) is set, uses batch
        compatibility scoring instead of per-vacancy filtering.
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

        keywords_counter: Counter[str] = Counter()
        skills_counter: Counter[str] = Counter()
        processed_vacancies: list[VacancyData] = []

        async def _scrape_one(
            client: httpx.AsyncClient,
            vac: dict,
        ) -> VacancyData:
            async with sem:
                page_data = await self._scraper.parse_vacancy_page(client, vac["url"])
            description = page_data.get("description", "")
            skills: list[str] = page_data.get("skills", [])
            async with scrape_lock:
                scraped_count[0] += 1
                scrape_current = scraped_count[0]
            if on_page_scraped:
                await on_page_scraped(scrape_current, total)
            return VacancyData(
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

        async with httpx.AsyncClient() as client:
            for batch_start in range(0, len(vacancies_to_process), _COMPAT_BATCH_SIZE):
                batch = vacancies_to_process[batch_start : batch_start + _COMPAT_BATCH_SIZE]
                partials = await asyncio.gather(*[_scrape_one(client, vac) for vac in batch])

                if compat_params is not None:
                    tech_stack, work_exp, threshold = compat_params
                    inputs = [
                        VacancyCompatInput(
                            hh_vacancy_id=p.hh_vacancy_id,
                            title=p.title,
                            skills=p.raw_skills,
                            description=p.description,
                        )
                        for p in partials
                    ]
                    async with ai_sem:
                        scores = await self._ai.calculate_compatibility_batch(
                            inputs,
                            user_tech_stack=tech_stack,
                            user_work_experience=work_exp,
                        )
                    passing = [p for p in partials if scores.get(p.hh_vacancy_id, 0) >= threshold]
                    for p in partials:
                        if p not in passing:
                            async with kw_lock:
                                kw_count[0] += 1
                                current = kw_count[0]
                            logger.info(
                                "Vacancy skipped (compat filter)",
                                index=current,
                                total=total,
                                title=p.title[:60],
                            )
                            if on_vacancy_processed:
                                await on_vacancy_processed(current, total, None)
                else:
                    passing = list(partials)

                for partial in passing:
                    ai_keywords: list[str] = []
                    if partial.description:
                        async with ai_sem:
                            ai_keywords = await self._ai.extract_keywords(partial.description)

                    async with kw_lock:
                        kw_count[0] += 1
                        current = kw_count[0]

                    logger.info(
                        "Vacancy processed",
                        index=current,
                        score=scores.get(partial.hh_vacancy_id, 0),
                        total=total,
                        title=partial.title[:60],
                        keywords_found=len(ai_keywords),
                        skills_found=len(partial.raw_skills),
                    )

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
                    processed_vacancies.append(vacancy_data)
                    for skill in partial.raw_skills:
                        skills_counter[skill.strip()] += 1
                    for kw in ai_keywords:
                        keywords_counter[kw.strip()] += 1

                    if on_vacancy_processed:
                        await on_vacancy_processed(current, total, vacancy_data)

        return PipelineResult(
            vacancies=processed_vacancies,
            keywords=keywords_counter.most_common(),
            skills=skills_counter.most_common(),
        )
