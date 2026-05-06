"""Orchestrates the keyword extraction pipeline for a parsing company."""

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable

import httpx

from src.config import settings
from src.core.logging import get_logger
from src.schemas.vacancy import PipelineResult, VacancyData, build_vacancy_api_context
from src.services.ai.client import AIClient, close_ai_client
from src.services.ai.prompts import VacancyCompatInput
from src.services.parser.scraper import HHScraper

logger = get_logger(__name__)

OnProgressCallback = Callable[[int, int, VacancyData | None], Awaitable[None]]
OnUrlsFetchedCallback = Callable[[list[dict]], Awaitable[None]]

# (tech_stack, work_exp_text, threshold) — when set, use batch compat instead of per-vacancy
CompatParams = tuple[list[str], str, int]

_DEFAULT_CONCURRENCY = settings.hh_vacancy_detail_concurrency
_AI_CONCURRENCY = 3
_COMPAT_BATCH_SIZE = 8
_COMPAT_FETCH_BATCH_SIZE = 50
_KEYWORD_BATCH_SIZE = 5


class ParsingExtractor:
    """Runs the full parsing + AI extraction pipeline."""

    def __init__(
        self,
        scraper: HHScraper | None = None,
        ai_client: AIClient | None = None,
        *,
        browser_storage_state: dict | None = None,
    ) -> None:
        self._scraper = scraper or HHScraper()
        self._ai = ai_client or AIClient()
        self._browser_storage_state = browser_storage_state

    @staticmethod
    def _vacancy_parse_mode() -> str:
        return "api" if settings.hh_api_vacancy_parsing_enabled else "web"

    def _http_client_kwargs(self) -> dict:
        if self._vacancy_parse_mode() == "web" and self._browser_storage_state:
            from src.services.hh_ui.applicant_http import httpx_cookies_from_storage_state

            return {
                "cookies": httpx_cookies_from_storage_state(self._browser_storage_state),
                "follow_redirects": True,
            }
        return {}

    async def aclose(self) -> None:
        await close_ai_client(self._ai)

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
        compatibility scoring. Search list pages are exhausted first (no detail
        fetches until the catalog slice is collected), then vacancies are processed.
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
                parse_mode=self._vacancy_parse_mode(),
                storage_state=self._browser_storage_state,
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
        """Pipeline with compat: exhaust search list URLs, then detail + compat + keywords."""
        blacklisted = blacklisted_ids or set()
        vacancies: list[dict] = []
        skip_count = 0

        if resume_from is not None:
            vacancies, skip_count = resume_from
        else:
            seen_ids: set[str] = set()
            start_page = 0
            while True:
                batch, next_page, has_more = await self._scraper.collect_vacancy_urls_batch(
                    base_url=search_url,
                    keyword=keyword_filter,
                    batch_size=_COMPAT_FETCH_BATCH_SIZE,
                    start_page=start_page,
                    blacklisted_ids=blacklisted,
                    exclude_ids=seen_ids if seen_ids else None,
                    storage_state=self._browser_storage_state,
                    parse_mode=self._vacancy_parse_mode(),
                )
                if not batch:
                    if not has_more:
                        break
                    logger.warning(
                        "Empty vacancy batch from search list; stopping collection",
                        has_more=has_more,
                        start_page=start_page,
                    )
                    break
                vacancies.extend(batch)
                seen_ids.update(v["hh_vacancy_id"] for v in batch)
                start_page = next_page
                if on_urls_fetched:
                    await on_urls_fetched(batch)
                if not has_more:
                    break

            if not vacancies:
                logger.warning("No vacancies found")
                return PipelineResult(vacancies=[], keywords=[], skills=[])

            logger.info(
                "Compat pipeline: finished collecting search URLs before detail fetch",
                total_urls=len(vacancies),
                target_count=target_count,
            )

        keywords_counter: Counter[str] = Counter()
        skills_counter: Counter[str] = Counter()
        processed_vacancies: list[VacancyData] = []

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
            detail_url = vac["url"]
            if not self._scraper._extract_vacancy_id(detail_url):
                detail_url = f"https://hh.ru/vacancy/{vac['hh_vacancy_id']}"
            async with sem:
                page_data = await self._scraper.parse_vacancy_page(
                    client,
                    detail_url,
                    parse_mode=self._vacancy_parse_mode(),
                    storage_state=self._browser_storage_state,
                )
            if not page_data:
                return VacancyData(
                    hh_vacancy_id=vac["hh_vacancy_id"],
                    url=vac["url"],
                    title=vac["title"],
                    raw_skills=[],
                    description="",
                    salary=vac.get("salary", ""),
                    company_name=vac.get("company_name", ""),
                )
            async with scrape_lock:
                scraped_count[0] += 1
                scrape_current = scraped_count[0]
            if on_page_scraped:
                await on_page_scraped(scrape_current, total)
            orm_fields = page_data.get("orm_fields", {})
            employer_data = page_data.get("employer_data", {})
            area_data = page_data.get("area_data", {})
            skills = page_data.get("skills", [])
            api_ctx = build_vacancy_api_context(orm_fields, employer_data, skills)
            return VacancyData(
                hh_vacancy_id=vac["hh_vacancy_id"],
                url=vac["url"],
                title=page_data.get("title", vac["title"]),
                raw_skills=skills,
                description=page_data.get("description", ""),
                salary=page_data.get("salary", vac.get("salary", "")),
                company_name=page_data.get("company_name", vac.get("company_name", "")),
                work_experience=page_data.get("work_experience", ""),
                employment_type=page_data.get("employment_type", ""),
                work_schedule=page_data.get("work_schedule", ""),
                work_formats=page_data.get("work_formats", ""),
                compensation_frequency=page_data.get("compensation_frequency", ""),
                working_hours=page_data.get("working_hours", ""),
                vacancy_api_context=api_ctx,
                employer_data=employer_data,
                area_data=area_data,
                orm_fields=orm_fields,
            )

        async with httpx.AsyncClient(**self._http_client_kwargs()) as client:
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
                            vacancy_api_context=p.vacancy_api_context,
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

                for chunk_start in range(0, len(passing), _KEYWORD_BATCH_SIZE):
                    chunk = passing[chunk_start : chunk_start + _KEYWORD_BATCH_SIZE]
                    kw_map: dict[str, list[str]] = {}

                    if len(chunk) == 1:
                        p = chunk[0]
                        if p.description or p.vacancy_api_context:
                            async with ai_sem:
                                kw_map[p.hh_vacancy_id] = await self._ai.extract_keywords(
                                    p.description,
                                    vacancy_api_context=p.vacancy_api_context,
                                )
                    else:
                        inputs = [
                            VacancyCompatInput(
                                hh_vacancy_id=p.hh_vacancy_id,
                                title=p.title,
                                skills=p.raw_skills,
                                description=p.description,
                                vacancy_api_context=p.vacancy_api_context,
                            )
                            for p in chunk
                        ]
                        async with ai_sem:
                            kw_map = await self._ai.extract_keywords_batch(inputs)

                        need_full_fallback = len(kw_map) < len(chunk)
                        if need_full_fallback:
                            for p in chunk:
                                if p.description or p.vacancy_api_context:
                                    async with ai_sem:
                                        kw_map[p.hh_vacancy_id] = await self._ai.extract_keywords(
                                            p.description,
                                            vacancy_api_context=p.vacancy_api_context,
                                        )
                        else:
                            for p in chunk:
                                has_content = bool(p.description or p.vacancy_api_context)
                                if has_content and kw_map.get(p.hh_vacancy_id, []) == []:
                                    async with ai_sem:
                                        kw_map[p.hh_vacancy_id] = await self._ai.extract_keywords(
                                            p.description,
                                            vacancy_api_context=p.vacancy_api_context,
                                        )

                    for partial in chunk:
                        ai_keywords = kw_map.get(partial.hh_vacancy_id, [])

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
                            vacancy_api_context=partial.vacancy_api_context,
                            employer_data=partial.employer_data,
                            area_data=partial.area_data,
                            orm_fields=partial.orm_fields,
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
