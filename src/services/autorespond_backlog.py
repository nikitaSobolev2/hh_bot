"""Detail-parse and AI-score pending autoparsed vacancies for streaming autorespond."""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import settings
from src.core.logging import get_logger
from src.core.system_load import get_system_load_guard
from src.models.autoparse import AutoparsedVacancy
from src.repositories.autoparse import AutoparsedVacancyRepository
from src.schemas.vacancy import build_vacancy_api_context_from_orm
from src.services.ai.client import AIClient, close_ai_client
from src.services.ai.prompts import VacancyCompatInput
from src.services.autoparse.compatibility import compatibility_score_needs_regeneration
from src.services.hh_ui.runner import normalize_hh_vacancy_url
from src.services.parser.hh_parser_service import HHParserService
from src.services.parser.scraper import HHCaptchaRequiredError
from src.worker.tasks.autoparse import (
    _ANALYSIS_BATCH_SIZE,
    _autoparse_pipeline_batch_size,
    _reuse_analysis_fields,
)

logger = get_logger(__name__)

_VACANCY_PROCESSING_LOCK_TTL = 600


def vacancy_needs_detail_parse(vacancy: AutoparsedVacancy) -> bool:
    """True when the row lacks full vacancy text and needs a detail fetch."""
    return not (getattr(vacancy, "description", None) or "").strip()


def _vacancy_to_fetch_card(vacancy: AutoparsedVacancy) -> dict[str, Any]:
    hh_id = str(vacancy.hh_vacancy_id or "")
    return {
        "hh_vacancy_id": hh_id,
        "url": normalize_hh_vacancy_url(vacancy.url, hh_id),
        "title": vacancy.title or "",
        "company_name": vacancy.company_name,
        "company_url": vacancy.company_url,
        "salary": vacancy.salary,
        "tags": vacancy.tags,
    }


def _compat_input_from_vacancy(
    vacancy: AutoparsedVacancy,
    *,
    description: str | None = None,
    raw_skills: list[str] | None = None,
) -> VacancyCompatInput:
    return VacancyCompatInput(
        hh_vacancy_id=str(vacancy.hh_vacancy_id or ""),
        title=vacancy.title or "",
        skills=list(raw_skills if raw_skills is not None else (vacancy.raw_skills or [])),
        description=description if description is not None else (vacancy.description or ""),
        vacancy_api_context=build_vacancy_api_context_from_orm(vacancy),
    )


def _detail_update_kwargs(vac_dict: dict[str, Any]) -> dict[str, Any]:
    of = vac_dict.get("orm_fields") or {}
    return {
        "description": vac_dict.get("description") or "",
        "raw_skills": vac_dict.get("raw_skills"),
        "needs_employer_questions": bool(of.get("has_test")),
        "title": vac_dict.get("title") or None,
        "company_name": vac_dict.get("company_name"),
        "company_url": vac_dict.get("company_url"),
        "salary": vac_dict.get("salary"),
        "compensation_frequency": vac_dict.get("compensation_frequency"),
        "work_experience": vac_dict.get("work_experience"),
        "employment_type": vac_dict.get("employment_type"),
        "work_schedule": vac_dict.get("work_schedule"),
        "working_hours": vac_dict.get("working_hours"),
        "work_formats": vac_dict.get("work_formats"),
        "tags": vac_dict.get("tags"),
        "snippet_requirement": of.get("snippet_requirement"),
        "snippet_responsibility": of.get("snippet_responsibility"),
        "experience_id": of.get("experience_id"),
        "experience_name": of.get("experience_name"),
        "schedule_id": of.get("schedule_id"),
        "schedule_name": of.get("schedule_name"),
        "employment_id": of.get("employment_id"),
        "employment_name": of.get("employment_name"),
        "employment_form_id": of.get("employment_form_id"),
        "employment_form_name": of.get("employment_form_name"),
        "salary_from": of.get("salary_from"),
        "salary_to": of.get("salary_to"),
        "salary_currency": of.get("salary_currency"),
        "salary_gross": of.get("salary_gross"),
        "address_raw": of.get("address_raw"),
        "address_city": of.get("address_city"),
        "address_street": of.get("address_street"),
        "address_building": of.get("address_building"),
        "address_lat": of.get("address_lat"),
        "address_lng": of.get("address_lng"),
        "metro_stations": of.get("metro_stations"),
        "vacancy_type_id": of.get("vacancy_type_id"),
        "published_at": of.get("published_at"),
        "work_format": of.get("work_format"),
        "professional_roles": of.get("professional_roles"),
    }


async def _acquire_vacancy_lock(
    worker_task: object | None,
    user_id: int,
    hh_vacancy_id: str,
) -> bool:
    if worker_task is None:
        return True
    acquire = getattr(worker_task, "acquire_user_vacancy_processing_lock", None)
    if acquire is None:
        return True
    return bool(
        await acquire(
            user_id,
            hh_vacancy_id,
            ttl=_VACANCY_PROCESSING_LOCK_TTL,
        )
    )


async def _release_vacancy_lock(
    worker_task: object | None,
    user_id: int,
    hh_vacancy_id: str,
) -> None:
    if worker_task is None:
        return
    release = getattr(worker_task, "release_user_vacancy_processing_lock", None)
    if release is None:
        return
    await release(user_id, hh_vacancy_id)


async def _detail_parse_vacancies(
    parser: HHParserService,
    vacancies: list[AutoparsedVacancy],
) -> dict[int, dict[str, Any]]:
    """Return autoparsed PK -> merged detail dict for rows that fetched successfully."""
    needs_detail = [v for v in vacancies if vacancy_needs_detail_parse(v)]
    if not needs_detail:
        return {}

    merged_by_id: dict[int, dict[str, Any]] = {}
    pipeline_batch = _autoparse_pipeline_batch_size()
    sem = asyncio.Semaphore(settings.hh_vacancy_detail_concurrency)

    async with parser.build_client() as client:
        for batch_start in range(0, len(needs_detail), pipeline_batch):
            batch = needs_detail[batch_start : batch_start + pipeline_batch]
            cards = [_vacancy_to_fetch_card(v) for v in batch]
            results = await parser.fetch_details_batch_slice(client, cards, sem)
            for vacancy, _card, merged in zip(batch, cards, results, strict=True):
                if isinstance(merged, HHCaptchaRequiredError):
                    raise merged
                if isinstance(merged, Exception) or merged is None:
                    logger.warning(
                        "streaming_autorespond_backlog_detail_failed",
                        company_id=vacancy.autoparse_company_id,
                        autoparsed_vacancy_id=vacancy.id,
                        hh_vacancy_id=vacancy.hh_vacancy_id,
                        error=str(merged) if merged is not None else "empty",
                    )
                    continue
                merged_by_id[int(vacancy.id)] = merged
    return merged_by_id


async def score_pending_vacancies(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    company_id: int,
    user_id: int,
    vacancies: list[AutoparsedVacancy],
    user_stack: list[str],
    user_exp: str,
    parse_mode: str,
    detail_parse_mode: str,
    web_storage: dict | None,
    worker_task: object | None = None,
) -> list[AutoparsedVacancy]:
    """Detail-parse (when needed), AI-score, and persist compatibility for pending rows."""
    stale = [
        v
        for v in vacancies
        if compatibility_score_needs_regeneration(v.compatibility_score)
    ]
    if not stale or not (user_stack or user_exp):
        return []

    parser = HHParserService(
        parse_mode=parse_mode,
        detail_parse_mode=detail_parse_mode,
        storage_state=web_storage,
    )
    detail_by_id = await _detail_parse_vacancies(parser, stale)
    scored: list[AutoparsedVacancy] = []
    ai_client = AIClient()

    try:
        for batch_start in range(0, len(stale), _ANALYSIS_BATCH_SIZE):
            batch = stale[batch_start : batch_start + _ANALYSIS_BATCH_SIZE]
            await get_system_load_guard().wait_if_overloaded(
                "streaming_autorespond_backlog_score"
            )

            prepared: list[
                tuple[AutoparsedVacancy, float | None, str | None, list[str] | None, dict[str, Any]]
            ] = []
            ai_batch: list[tuple[AutoparsedVacancy, VacancyCompatInput]] = []
            locked_hh_ids: list[str] = []

            async with session_factory() as session:
                repo = AutoparsedVacancyRepository(session)
                for vacancy in batch:
                    hh_id = str(vacancy.hh_vacancy_id or "")
                    if not hh_id:
                        continue

                    detail_fields: dict[str, Any] = {}
                    merged = detail_by_id.get(int(vacancy.id))
                    if merged is not None:
                        detail_fields = _detail_update_kwargs(merged)

                    reusable = await repo.get_analyzed_for_user_hh_id(
                        user_id,
                        hh_id,
                        exclude_company_id=company_id,
                    )
                    if reusable is not None:
                        compat_score, ai_summary, ai_stack = _reuse_analysis_fields(reusable)
                        prepared.append(
                            (vacancy, compat_score, ai_summary, ai_stack, detail_fields)
                        )
                        continue

                    if not await _acquire_vacancy_lock(worker_task, user_id, hh_id):
                        reusable = await repo.get_analyzed_for_user_hh_id(
                            user_id,
                            hh_id,
                            exclude_company_id=company_id,
                        )
                        if reusable is not None:
                            compat_score, ai_summary, ai_stack = _reuse_analysis_fields(reusable)
                            prepared.append(
                                (vacancy, compat_score, ai_summary, ai_stack, detail_fields)
                            )
                        continue

                    locked_hh_ids.append(hh_id)
                    if merged is not None:
                        compat_input = VacancyCompatInput(
                            hh_vacancy_id=hh_id,
                            title=merged.get("title") or vacancy.title or "",
                            skills=list(merged.get("raw_skills") or []),
                            description=merged.get("description") or "",
                            vacancy_api_context=merged.get("vacancy_api_context"),
                        )
                    else:
                        compat_input = _compat_input_from_vacancy(vacancy)
                    ai_batch.append((vacancy, compat_input))

            analyses: dict[str, Any] = {}
            try:
                if ai_batch:
                    analyses = await ai_client.analyze_vacancies_batch(
                        [item[1] for item in ai_batch],
                        user_tech_stack=user_stack,
                        user_work_experience=user_exp,
                    )
                for vacancy, compat_input in ai_batch:
                    analysis = analyses.get(compat_input.hh_vacancy_id)
                    if analysis is None:
                        detail_fields = _detail_update_kwargs(detail_by_id.get(int(vacancy.id), {}))
                        prepared.append((vacancy, None, None, None, detail_fields))
                        continue
                    detail_fields = _detail_update_kwargs(
                        detail_by_id.get(int(vacancy.id), {})
                    )
                    prepared.append(
                        (
                            vacancy,
                            analysis.compatibility_score,
                            analysis.summary or None,
                            analysis.stack or None,
                            detail_fields,
                        )
                    )
            finally:
                for hh_vacancy_id in locked_hh_ids:
                    await _release_vacancy_lock(worker_task, user_id, hh_vacancy_id)

            async with session_factory() as session:
                repo = AutoparsedVacancyRepository(session)
                for vacancy, compat_score, ai_summary, ai_stack, detail_fields in prepared:
                    existing = await repo.get_by_id(int(vacancy.id))
                    if existing is None:
                        continue
                    update_kwargs = dict(detail_fields) if detail_fields else {}
                    if (
                        compat_score is not None
                        or ai_summary is not None
                        or ai_stack is not None
                    ):
                        update_kwargs.update(
                            {
                                "compatibility_score": compat_score,
                                "ai_summary": ai_summary,
                                "ai_stack": ai_stack,
                            }
                        )
                    if update_kwargs:
                        await repo.update(existing, **update_kwargs)
                        vacancy.compatibility_score = existing.compatibility_score
                        vacancy.ai_summary = existing.ai_summary
                        vacancy.ai_stack = existing.ai_stack
                        for field, value in detail_fields.items():
                            if value is not None and hasattr(vacancy, field):
                                setattr(vacancy, field, value)
                        if not compatibility_score_needs_regeneration(
                            vacancy.compatibility_score
                        ):
                            scored.append(vacancy)
                await session.commit()
    finally:
        await close_ai_client(ai_client)

    logger.info(
        "streaming_autorespond_backlog_scored",
        company_id=company_id,
        requested=len(stale),
        scored=len(scored),
    )
    return scored
