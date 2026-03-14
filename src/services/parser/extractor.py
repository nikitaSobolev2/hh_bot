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
OnUrlsFetchedCallback = Callable[[list[dict]], Awaitable[None]]

# (tech_stack, work_exp_text, threshold) — when set, use batch compat instead of per-vacancy
CompatParams = tuple[list[str], str, int]

_DEFAULT_CONCURRENCY = 15
_AI_CONCURRENCY = 3
_COMPAT_BATCH_SIZE = 8
_COMPAT_FETCH_BATCH_SIZE = 50


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
        on_urls_fetched: OnUrlsFetchedCallback | None = None,
        compat_params: CompatParams | None = None,
        concurrency: int = _DEFAULT_CONCURRENCY,
        ai_concurrency: int = _AI_CONCURRENCY,
        resume_from: tuple[list[dict], int] | None = None,
    ) -> PipelineResult:
        """Run the parsing pipeline.

        When resume_from is provided as (urls, skip_count), use the given URLs
        and skip the first skip_count (already processed). No scraping is done.

        When compat_params (tech_stack, work_exp, threshold) is set, uses batch
        compatibility scoring and fetches replacement batches until target_count
        passing vacancies or no more pages.
        """
        if compat_params is not None:
            return await self._run_pipeline_with_compat(
                search_url=search_url,
                keyword_filter=keyword_filter,
                target_count=target_count,
                blacklisted_ids=blacklisted_ids,
                on_page_scraped=on_page_scraped,
                on_vacancy_processed=on_vacancy_processed,
                on_urls_fetched=on_urls_fetched,
                compat_params=compat_params,
                concurrency=concurrency,
                ai_concurrency=ai_concurrency,
                resume_from=resume_from,
            )
        return await self._run_pipeline_one_shot(
            search_url=search_url,
            keyword_filter=keyword_filter,
            target_count=target_count,
            blacklisted_ids=blacklisted_ids,
            on_page_scraped=on_page_scraped,
            on_vacancy_processed=on_vacancy_processed,
            concurrency=concurrency,
            ai_concurrency=ai_concurrency,
            resume_from=resume_from,
        )

    async def _run_pipeline_one_shot(
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
        resume_from: tuple[list[dict], int] | None = None,
    ) -> PipelineResult:
        """One-shot pipeline: no compat filter, no fetch-more loop."""
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

        return await self._process_vacancy_batch(
            vacancies=vacancies,
            skip_count=skip_count,
            on_page_scraped=on_page_scraped,
            on_vacancy_processed=on_vacancy_processed,
            compat_params=None,
            concurrency=concurrency,
            ai_concurrency=ai_concurrency,
        )

    async def _run_pipeline_with_compat(
        self,
        search_url: str,
        keyword_filter: str,
        target_count: int,
        *,
        blacklisted_ids: set[str] | None = None,
        on_page_scraped: OnProgressCallback | None = None,
        on_vacancy_processed: OnProgressCallback | None = None,
        on_urls_fetched: OnUrlsFetchedCallback | None = None,
        compat_params: CompatParams,
        concurrency: int = _DEFAULT_CONCURRENCY,
        ai_concurrency: int = _AI_CONCURRENCY,
        resume_from: tuple[list[dict], int] | None = None,
    ) -> PipelineResult:
        """Pipeline with compat: fetch replacement batches until target_count or exhausted."""
        blacklisted = blacklisted_ids or set()
        vacancies: list[dict] = []
        skip_count = 0
        start_page = 0

        if resume_from is not None:
            vacancies, skip_count = resume_from
            seen_ids = {v["hh_vacancy_id"] for v in vacancies}
            start_page = 0

        if not vacancies:
            batch, next_page, has_more = await self._scraper.collect_vacancy_urls_batch(
                base_url=search_url,
                keyword=keyword_filter,
                batch_size=min(_COMPAT_FETCH_BATCH_SIZE, target_count * 2),
                start_page=0,
                blacklisted_ids=blacklisted,
                exclude_ids=None,
            )
            if not batch:
                logger.warning("No vacancies found")
                return PipelineResult(vacancies=[], keywords=[], skills=[])
            vacancies.extend(batch)
            seen_ids = {v["hh_vacancy_id"] for v in vacancies}
            start_page = next_page
            if on_urls_fetched:
                await on_urls_fetched(batch)

        else:
            seen_ids = {v["hh_vacancy_id"] for v in vacancies}

        keywords_counter: Counter[str] = Counter()
        skills_counter: Counter[str] = Counter()
        processed_vacancies: list[VacancyData] = []

        while True:
            await self._process_vacancy_batch(
                vacancies=vacancies,
                skip_count=skip_count,
                on_page_scraped=on_page_scraped,
                on_vacancy_processed=on_vacancy_processed,
                compat_params=compat_params,
                concurrency=concurrency,
                ai_concurrency=ai_concurrency,
                keywords_counter=keywords_counter,
                skills_counter=skills_counter,
                processed_vacancies=processed_vacancies,
            )
            skip_count = len(vacancies)

            if len(processed_vacancies) >= target_count:
                break

            batch, next_page, has_more = await self._scraper.collect_vacancy_urls_batch(
                base_url=search_url,
                keyword=keyword_filter,
                batch_size=_COMPAT_FETCH_BATCH_SIZE,
                start_page=start_page,
                blacklisted_ids=blacklisted,
                exclude_ids=seen_ids,
            )
            if not batch:
                break
            vacancies.extend(batch)
            seen_ids.update(v["hh_vacancy_id"] for v in batch)
            start_page = next_page
            if on_urls_fetched:
                await on_urls_fetched(batch)

            if not has_more:
                await self._process_vacancy_batch(
                    vacancies=vacancies,
                    skip_count=skip_count,
                    on_page_scraped=on_page_scraped,
                    on_vacancy_processed=on_vacancy_processed,
                    compat_params=compat_params,
                    concurrency=concurrency,
                    ai_concurrency=ai_concurrency,
                    keywords_counter=keywords_counter,
                    skills_counter=skills_counter,
                    processed_vacancies=processed_vacancies,
                )
                break

        return PipelineResult(
            vacancies=processed_vacancies,
            keywords=keywords_counter.most_common(),
            skills=skills_counter.most_common(),
        )

    async def _process_vacancy_batch(
        self,
        *,
        vacancies: list[dict],
        skip_count: int,
        on_page_scraped: OnProgressCallback | None,
        on_vacancy_processed: OnProgressCallback | None,
        compat_params: CompatParams | None,
        concurrency: int,
        ai_concurrency: int,
        keywords_counter: Counter[str] | None = None,
        skills_counter: Counter[str] | None = None,
        processed_vacancies: list[VacancyData] | None = None,
    ) -> PipelineResult:
        """Process a batch of vacancies: scrape, compat filter, keyword extract."""
        total = len(vacancies)
        vacancies_to_process = vacancies[skip_count:]
        sem = asyncio.Semaphore(concurrency)
        ai_sem = asyncio.Semaphore(ai_concurrency)

        scrape_lock = asyncio.Lock()
        scraped_count = [skip_count]
        kw_lock = asyncio.Lock()
        kw_count = [skip_count]

        if keywords_counter is None:
            keywords_counter = Counter()
        if skills_counter is None:
            skills_counter = Counter()
        if processed_vacancies is None:
            processed_vacancies = []

        if skip_count > 0 and on_page_scraped:
            await on_page_scraped(total, total)

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
                    scores = {}

                for partial in passing:
                    ai_keywords: list[str] = []
                    if partial.description:
                        async with ai_sem:
                            ai_keywords = await self._ai.extract_keywords(partial.description)

                    async with kw_lock:
                        kw_count[0] += 1
                        current = kw_count[0]

                    score = scores.get(partial.hh_vacancy_id, 0) if compat_params else 0
                    logger.info(
                        "Vacancy processed",
                        index=current,
                        score=score,
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
