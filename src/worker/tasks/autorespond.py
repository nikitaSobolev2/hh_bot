"""Celery tasks for the autorespond pipeline (dispatcher + recovery + compat shims).

Architecture
------------
The pipeline runs in three roles, each on its own worker process / queue:

1. **Dispatcher** (``autorespond.dispatch`` on queue ``celery``): filters candidates,
   picks resumes (bounded AI), fans out cover-letter pregenerate tasks, returns in seconds.

2. **Cover letter pre-gen** (``cover_letter.pregenerate_for_apply`` on queue
   ``cover_letter``): one task per vacancy; stores the letter in DB + Redis, then enqueues
   the apply unit and kicks the pump. Defined in :mod:`src.worker.tasks.cover_letter`.

3. **Apply pump** (``autorespond.apply_pump`` on queue ``hh_ui``): single consumer
   that pops batches from the ZSET, runs Playwright, ticks progress. Defined in
   :mod:`src.worker.tasks.hh_ui_apply`.

A ``autorespond.recover_stalled`` beat task heals abandoned runs (worker SIGKILL).

The old ``run_autorespond_company`` and pipeline entry-points are kept as thin
compat shims that delegate to :func:`dispatch_autorespond`.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.bot.modules.autoparse import autorespond_logic
from src.config import settings
from src.core.logging import get_logger
from src.core.system_load import get_system_load_guard
from src.models.autoparse import AutoparsedVacancy
from src.repositories.app_settings import AppSettingRepository
from src.repositories.autoparse import AutoparseCompanyRepository, AutoparsedVacancyRepository
from src.repositories.hh_application_attempt import HhApplicationAttemptRepository
from src.repositories.vacancy_feed import VacancyFeedSessionRepository
from src.services.autorespond_pipeline_state import (
    clear_all_pipeline_state,
    get_pump_lock_owner_sync,
    iter_active_pipeline_envelopes,
    load_pipeline_envelope,
    mark_pregen_pending,
    pump_heartbeat_age_seconds,
    ready_remaining_count,
    save_pipeline_envelope,
)
from src.services.hh_ui.rate_limit import (
    current_ui_apply_count_sync,
    get_hh_ui_apply_max_per_day_effective,
    remaining_ui_apply_slots_sync,
)
from src.services.hh_ui.runner import normalize_hh_vacancy_url
from src.worker.app import celery_app
from src.worker.base_task import HHBotTask
from src.worker.tasks.negotiations_sync import _sync_negotiations_async
from src.worker.utils import run_async

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Bounded helpers (preserved so the pipeline cannot wedge on external calls)
# ---------------------------------------------------------------------------


async def _tick_autorespond_bar_bounded(**kwargs) -> None:
    """Progress bar update with wall-clock cap so Telegram stalls cannot block dispatch."""
    from src.services.autorespond_progress import tick_autorespond_bar

    try:
        await asyncio.wait_for(
            tick_autorespond_bar(**kwargs),
            timeout=settings.autorespond_progress_tick_timeout_seconds,
        )
    except TimeoutError:
        logger.warning(
            "autorespond_progress_tick_timeout",
            chat_id=kwargs.get("chat_id"),
            task_key=kwargs.get("task_key"),
            timeout_s=settings.autorespond_progress_tick_timeout_seconds,
        )


async def _resolve_resume_for_autorespond_bounded(
    cover_ai_client,
    vac,
    resume_items: list[dict[str, str]],
    *,
    stored_autorespond_resume_id: str | None,
):
    from src.services.ai.resume_selection import (
        fallback_resume_id,
        resolve_resume_id_for_autorespond_vacancy,
    )

    try:
        return await asyncio.wait_for(
            resolve_resume_id_for_autorespond_vacancy(
                cover_ai_client,
                vac,
                resume_items,
                stored_autorespond_resume_id=stored_autorespond_resume_id,
            ),
            timeout=settings.autorespond_resume_resolve_timeout_seconds,
        )
    except TimeoutError:
        picked = fallback_resume_id(resume_items, stored_autorespond_resume_id)
        logger.warning(
            "autorespond_resume_resolve_timeout",
            vacancy_id=vac.id,
            hh_vacancy_id=vac.hh_vacancy_id,
            resume_id_prefix=picked[:12],
            timeout_s=settings.autorespond_resume_resolve_timeout_seconds,
        )
        return picked


# ---------------------------------------------------------------------------
# Compat: keep public types referenced by other modules / tests
# ---------------------------------------------------------------------------


def _autorespond_filter_rejection_counts(
    raw: list[AutoparsedVacancy],
    *,
    min_compat: int,
    company_keyword_filter: str,
    keyword_mode: str,
    allow_missing_compatibility_score: bool,
) -> tuple[int, int]:
    compat_rejected = 0
    keyword_rejected = 0
    for v in raw:
        if not autorespond_logic.vacancy_passes_compatibility(
            v,
            min_compat,
            allow_missing_score=allow_missing_compatibility_score,
        ):
            compat_rejected += 1
            continue
        if not autorespond_logic.vacancy_passes_keyword_mode(
            v, company_keyword_filter, keyword_mode
        ):
            keyword_rejected += 1
    return compat_rejected, keyword_rejected


def _compatibility_score_value(score: object) -> float | None:
    if score is None:
        return None
    try:
        value = float(score)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return value


def _compatibility_bucket_label(score: float) -> str:
    if score < 25:
        return "0_24"
    if score < 50:
        return "25_49"
    if score < 75:
        return "50_74"
    return "75_100"


def _compatibility_log_metrics(vacancies: list[AutoparsedVacancy]) -> dict[str, object]:
    histogram = {"0_24": 0, "25_49": 0, "50_74": 0, "75_100": 0}
    scores: list[float] = []
    missing = 0
    for vacancy in vacancies:
        score = _compatibility_score_value(getattr(vacancy, "compatibility_score", None))
        if score is None:
            missing += 1
            continue
        scores.append(score)
        histogram[_compatibility_bucket_label(score)] += 1
    average = round(sum(scores) / len(scores), 2) if scores else None
    return {
        "average_percent": average,
        "missing_count": missing,
        "histogram": histogram,
    }


async def _load_candidates(
    session: AsyncSession,
    company_id: int,
    vacancy_ids: list[int] | None,
    task_started_at: datetime | None,
) -> list[AutoparsedVacancy]:
    repo = AutoparsedVacancyRepository(session)
    if vacancy_ids is not None:
        return await repo.get_by_ids_for_company(company_id, vacancy_ids)
    stmt = (
        select(AutoparsedVacancy)
        .where(AutoparsedVacancy.autoparse_company_id == company_id)
        .order_by(AutoparsedVacancy.id.desc())
        .limit(500)
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    if task_started_at is None:
        return rows
    return [v for v in rows if v.created_at and v.created_at >= task_started_at]


async def _regenerate_missing_compatibility_scores(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: int,
    vacancies: list[AutoparsedVacancy],
    user_stack: list[str],
    user_exp: str,
) -> None:
    """Fill stale compatibility scores (NULL/0) before filtering."""
    from src.repositories.autoparse import AutoparsedVacancyRepository
    from src.schemas.vacancy import build_vacancy_api_context_from_orm
    from src.services.ai.client import AIClient, close_ai_client
    from src.services.ai.prompts import VacancyCompatInput
    from src.services.autoparse.compatibility import compatibility_score_needs_regeneration

    stale_ids = [
        v.id for v in vacancies if compatibility_score_needs_regeneration(v.compatibility_score)
    ]
    if not stale_ids or not (user_stack or user_exp):
        return

    originals_by_id = {v.id: v for v in vacancies}

    from sqlalchemy.orm import selectinload

    async with session_factory() as session:
        stmt = (
            select(AutoparsedVacancy)
            .where(AutoparsedVacancy.id.in_(stale_ids))
            .options(selectinload(AutoparsedVacancy.employer))
        )
        result = await session.execute(stmt)
        stale = list(result.scalars().all())

    ai_client = AIClient()
    try:
        analyses = await ai_client.analyze_vacancies_batch(
            [
                VacancyCompatInput(
                    hh_vacancy_id=v.hh_vacancy_id,
                    title=v.title or "",
                    skills=v.raw_skills or [],
                    description=v.description or "",
                    vacancy_api_context=build_vacancy_api_context_from_orm(v),
                )
                for v in stale
            ],
            user_tech_stack=user_stack,
            user_work_experience=user_exp,
        )

        async with session_factory() as session:
            repo = AutoparsedVacancyRepository(session)
            for vacancy in stale:
                analysis = analyses.get(vacancy.hh_vacancy_id)
                if analysis is None:
                    continue
                await repo.update(
                    vacancy,
                    compatibility_score=analysis.compatibility_score,
                    ai_summary=analysis.summary or None,
                    ai_stack=analysis.stack or None,
                )
                orig = originals_by_id.get(vacancy.id)
                if orig is not None:
                    orig.compatibility_score = analysis.compatibility_score
                    orig.ai_summary = analysis.summary or None
                    orig.ai_stack = analysis.stack or None
            await session.commit()
    except Exception as exc:
        logger.warning(
            "autorespond_pre_filter_compat_regeneration_failed",
            user_id=user_id,
            vacancies=len(stale_ids),
            error=str(exc),
        )
    finally:
        await close_ai_client(ai_client)


async def _unreacted_autoparsed_vacancy_ids(
    session_factory: async_sessionmaker[AsyncSession],
    company_id: int,
    user_id: int,
) -> list[int]:
    """Autoparsed PKs for this company that the user has not liked/disliked in any feed."""
    async with session_factory() as session:
        feed_repo = VacancyFeedSessionRepository(session)
        reacted = await feed_repo.get_all_reacted_vacancy_ids(user_id, company_id)
        stmt = select(AutoparsedVacancy.id).where(
            AutoparsedVacancy.autoparse_company_id == company_id,
        )
        if reacted:
            stmt = stmt.where(AutoparsedVacancy.id.notin_(list(reacted)))
        stmt = stmt.order_by(AutoparsedVacancy.id.desc())
        result = await session.execute(stmt)
        return [int(row[0]) for row in result.all()]


async def _pending_autorespond_autoparsed_vacancy_ids(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    company_id: int,
    user_id: int,
    hh_linked_account_id: int,
) -> list[int]:
    """Autoparsed PKs not yet successfully applied (feed likes still eligible).

    Unlike :func:`_unreacted_autoparsed_vacancy_ids`, liked-but-not-applied vacancies
    are included. Only explicit feed dislikes and prior success / employer-question
    attempts are excluded.
    """
    async with session_factory() as session:
        feed_repo = VacancyFeedSessionRepository(session)
        attempt_repo = HhApplicationAttemptRepository(session)
        disliked = await feed_repo.get_disliked_vacancy_ids_for_user_company(
            user_id,
            company_id,
        )
        stmt = (
            select(
                AutoparsedVacancy.id,
                AutoparsedVacancy.hh_vacancy_id,
                AutoparsedVacancy.needs_employer_questions,
            )
            .where(AutoparsedVacancy.autoparse_company_id == company_id)
            .order_by(AutoparsedVacancy.id.desc())
        )
        rows = list((await session.execute(stmt)).all())
        if not rows:
            return []

        hh_ids = [str(row[1]) for row in rows if row[1] is not None]
        handled = await attempt_repo.hh_vacancy_ids_with_success_or_employer_questions(
            user_id,
            hh_linked_account_id,
            hh_ids,
        )

    pending: list[int] = []
    for vacancy_id, hh_vacancy_id, needs_employer_questions in rows:
        if vacancy_id in disliked:
            continue
        if needs_employer_questions:
            continue
        if hh_vacancy_id is not None and str(hh_vacancy_id) in handled:
            continue
        pending.append(int(vacancy_id))
    return pending


def _merge_manual_pipeline_vacancy_ids(*id_groups: list[int]) -> list[int]:
    if not id_groups or not any(id_groups):
        return []
    merged_ids = {int(vacancy_id) for group in id_groups for vacancy_id in group}
    return sorted(merged_ids, reverse=True)


async def _manual_pipeline_autorespond_vacancy_ids(
    session_factory: async_sessionmaker[AsyncSession],
    company_id: int,
    user_id: int,
    hh_linked_account_id: int,
    new_vacancy_ids: list[int],
    scraped_hh_vacancy_ids: list[str] | None = None,
) -> list[int]:
    pending_ids = await _pending_autorespond_autoparsed_vacancy_ids(
        session_factory,
        company_id=company_id,
        user_id=user_id,
        hh_linked_account_id=hh_linked_account_id,
    )
    scraped_ids: list[int] = []
    if scraped_hh_vacancy_ids:
        async with session_factory() as session:
            vacancy_repo = AutoparsedVacancyRepository(session)
            scraped_ids = await vacancy_repo.list_ids_by_company_and_hh_vacancy_ids(
                company_id,
                {str(hh_id) for hh_id in scraped_hh_vacancy_ids if hh_id},
            )
    merged_ids = _merge_manual_pipeline_vacancy_ids(
        new_vacancy_ids,
        pending_ids,
        scraped_ids,
    )
    logger.info(
        "manual_pipeline_candidate_ids",
        company_id=company_id,
        user_id=user_id,
        new_ids=len(new_vacancy_ids),
        pending_ids=len(pending_ids),
        scraped_ids=len(scraped_ids),
        merged_ids=len(merged_ids),
    )
    return merged_ids


async def _run_negotiations_sync_with_retry(
    session_factory: async_sessionmaker[AsyncSession],
    sync_task: HHBotTask | None,
    *,
    user_id: int,
    hh_acc_id: int,
    company_id: int,
    telegram_id: int,
    locale: str,
    trigger: str,
) -> dict:
    from src.worker.hh_captcha_retry import hh_captcha_retry_delay

    attempt = 0
    cached_vacancy_ids: set[str] | None = None
    while True:
        sync_res = await _sync_negotiations_async(
            session_factory,
            sync_task,
            user_id,
            hh_acc_id,
            company_id,
            telegram_id,
            locale,
            notify_user=False,
            prefetched_vacancy_ids=cached_vacancy_ids,
        )
        returned_vacancy_ids = sync_res.get("vacancy_ids")
        if returned_vacancy_ids:
            cached_vacancy_ids = {str(vacancy_id) for vacancy_id in returned_vacancy_ids}
        if sync_res.get("status") != "error" or sync_res.get("reason") != "captcha_required":
            return sync_res
        wait_seconds = hh_captcha_retry_delay(attempt)
        logger.warning(
            "autorespond_negotiations_sync_retry_wait",
            company_id=company_id,
            user_id=user_id,
            trigger=trigger,
            attempt=attempt + 1,
            wait_seconds=wait_seconds,
            cached_vacancy_ids=len(cached_vacancy_ids or ()),
        )
        await asyncio.sleep(wait_seconds)
        attempt += 1


async def _run_autorespond_after_manual_parse_async(
    session_factory: async_sessionmaker[AsyncSession],
    company_id: int,
    user_id: int,
) -> dict:
    """After manual autoparse completes: enqueue dispatcher for pending autorespond vacancies."""
    async with session_factory() as session:
        settings_repo = AppSettingRepository(session)
        if not await settings_repo.get_value("task_autorespond_enabled", default=False):
            return {"status": "skipped", "reason": "autorespond_disabled_global"}
        company_repo = AutoparseCompanyRepository(session)
        company = await company_repo.get_by_id(company_id)
        if not company or company.is_deleted or company.user_id != user_id:
            return {"status": "skipped", "reason": "company_invalid"}
        if not company.autorespond_enabled:
            return {"status": "skipped", "reason": "autorespond_disabled_company"}
        if not company.autorespond_hh_linked_account_id:
            return {"status": "skipped", "reason": "autorespond_not_configured"}
        from src.repositories.hh_linked_account import HhLinkedAccountRepository
        from src.services.ai.resume_selection import normalize_hh_resume_cache_items

        hh_acc_repo = HhLinkedAccountRepository(session)
        hh_acc = await hh_acc_repo.get_by_id(company.autorespond_hh_linked_account_id)
        if not hh_acc or not normalize_hh_resume_cache_items(hh_acc.resume_list_cache):
            return {"status": "skipped", "reason": "autorespond_not_configured"}

    ids = await _pending_autorespond_autoparsed_vacancy_ids(
        session_factory,
        company_id=company_id,
        user_id=user_id,
        hh_linked_account_id=company.autorespond_hh_linked_account_id,
    )
    if not ids:
        logger.info(
            "manual_chain_no_pending_autorespond",
            company_id=company_id,
            user_id=user_id,
        )
        return {"status": "no_pending", "vacancy_ids": []}

    dispatch_autorespond.delay(
        company_id,
        vacancy_ids=ids,
        trigger="manual_unreacted",
    )
    logger.info(
        "manual_chain_autorespond_enqueued",
        company_id=company_id,
        user_id=user_id,
        count=len(ids),
    )
    return {"status": "enqueued", "vacancy_count": len(ids), "vacancy_ids": ids}


# ---------------------------------------------------------------------------
# Dispatcher (new): seeds Redis state, fans out pregens, kicks the pump
# ---------------------------------------------------------------------------


async def _start_or_update_progress_bar(
    *,
    celery_task,
    user,
    company,
    locale: str,
    pipeline_context: dict | None,
    suppress_progress: bool,
    progress_task_key: str | None,
    work_units: int,
    celery_id: str,
) -> tuple[object | None, str | None, object | None, int, bool]:
    """Create / reuse the progress bar. Returns ``(svc, task_key, bot, bar_index, is_pipeline)``."""
    from src.core.i18n import get_text
    from src.services.progress_service import ProgressService, create_progress_redis

    use_pipeline = pipeline_context is not None
    is_task_group_pipeline = bool(
        pipeline_context and pipeline_context.get("task_group")
    )
    if suppress_progress and not use_pipeline:
        return None, None, None, 0, False
    if use_pipeline:
        progress = pipeline_context["svc"]
        task_key = str(pipeline_context["task_key"])
        progress_bot = pipeline_context["bot"]
        progress_bar_index = int(pipeline_context.get("bar_index", 0))
        return progress, task_key, progress_bot, progress_bar_index, is_task_group_pipeline

    if not (celery_task and user.telegram_id and user.telegram_id > 0):
        return None, None, None, 0, False

    task_key = progress_task_key or f"autorespond:{company.id}:{celery_id}"
    progress_bot = celery_task.create_bot()
    progress = ProgressService(progress_bot, user.telegram_id, create_progress_redis(), locale)
    await progress.start_task(
        task_key=task_key,
        title=company.vacancy_title,
        bar_labels=[get_text("progress-bar-autorespond", locale)],
        celery_task_id=celery_id,
        initial_totals=[max(0, work_units)],
        steps=[
            {
                "id": "negotiations",
                "label": get_text("progress-step-negotiations-sync", locale),
                "state": "running",
            },
            {
                "id": "applications",
                "label": get_text("progress-step-autorespond-applications", locale),
                "state": "pending",
            },
        ],
        active_step_index=0,
    )
    return progress, task_key, progress_bot, 0, False


async def _run_autorespond_async(
    session_factory: async_sessionmaker[AsyncSession],
    celery_task: object | None,
    company_id: int,
    vacancy_ids: list[int] | None,
    trigger: str,
    task_started_at: datetime | None,
    *,
    pipeline_context: dict | None = None,
    suppress_progress: bool = False,
    progress_task_key: str | None = None,
) -> dict:
    """Filter candidates, pick resumes, seed pipeline state, kick pump, return.

    The dispatcher never iterates per-vacancy work synchronously. All Playwright
    + cover-letter work happens on other queues by the time this returns.
    """
    from src.bot.modules.autoparse import services as ap_service
    from src.core.constants import AppSettingKey
    from src.core.i18n import get_text
    from src.repositories.autoparse import AutoparseCompanyRepository
    from src.repositories.hh_linked_account import HhLinkedAccountRepository
    from src.repositories.user import UserRepository
    from src.services.ai.client import AIClient, close_ai_client
    from src.services.ai.resume_selection import normalize_hh_resume_cache_items
    from src.services.autorespond_progress import (
        clear_autorespond_done_counter,
        clear_autorespond_employer_test_counter,
        clear_autorespond_failed_counter,
        clear_hh_ui_batch_checkpoint_sync,
        clear_hh_ui_resume_envelope_sync,
        hh_ui_batch_resume_payload,
    )

    async with session_factory() as session:
        settings_repo = AppSettingRepository(session)
        if not await settings_repo.get_value("task_autorespond_enabled", default=False):
            logger.info(
                "autorespond_exit",
                company_id=company_id,
                trigger=trigger,
                reason="disabled_global",
            )
            return {"status": "disabled_global"}

        company_repo = AutoparseCompanyRepository(session)
        company = await company_repo.get_by_id(company_id)
        if not company or company.is_deleted:
            return {"status": "company_not_found"}
        if not company.autorespond_enabled:
            return {"status": "disabled_company"}
        if not company.autorespond_hh_linked_account_id:
            return {"status": "not_configured"}

        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(company.user_id)
        if not user:
            return {"status": "user_not_found"}

        hh_acc_id = company.autorespond_hh_linked_account_id
        hh_acc_repo = HhLinkedAccountRepository(session)
        hh_linked = await hh_acc_repo.get_by_id(hh_acc_id)
        if not hh_linked:
            return {"status": "not_configured"}
        resume_items = normalize_hh_resume_cache_items(hh_linked.resume_list_cache)
        if not resume_items:
            return {"status": "not_configured"}

        locale = user.language_code or "ru"
        cid = getattr(celery_task, "request", None)
        celery_id = str(getattr(cid, "id", None) or "local") if celery_task else "local"

        ap_settings = await ap_service.get_user_autoparse_settings(session, user.id)
        cover_letter_style = ap_settings.get("cover_letter_style", "professional")
        cover_task_enabled = bool(
            await settings_repo.get_value(AppSettingKey.TASK_COVER_LETTER_ENABLED, default=True)
        )
        from src.repositories.work_experience import WorkExperienceRepository
        from src.worker.tasks.autoparse import _build_user_profile

        work_experiences = await WorkExperienceRepository(session).get_active_by_user(user.id)
        user_stack, user_exp = _build_user_profile(ap_settings, work_experiences)

    progress, task_key, progress_bot, progress_bar_index, is_task_group_pipeline = (
        await _start_or_update_progress_bar(
            celery_task=celery_task,
            user=user,
            company=company,
            locale=locale,
            pipeline_context=pipeline_context,
            suppress_progress=suppress_progress,
            progress_task_key=progress_task_key,
            work_units=0,
            celery_id=celery_id,
        )
    )

    if is_task_group_pipeline and progress and task_key:
        await progress.set_nested_steps(
            task_key,
            [
                {
                    "id": "negotiations",
                    "label": get_text("progress-step-negotiations-sync", locale),
                    "state": "running",
                },
                {
                    "id": "applications",
                    "label": get_text("progress-step-autorespond-applications", locale),
                    "state": "pending",
                },
            ],
            active_index=0,
        )
        await progress.update_bar(task_key, progress_bar_index, 0, 1)

    sync_task = celery_task if isinstance(celery_task, HHBotTask) else None
    sync_res = await _run_negotiations_sync_with_retry(
        session_factory,
        sync_task,
        user_id=user.id,
        hh_acc_id=hh_acc_id,
        company_id=company_id,
        telegram_id=user.telegram_id,
        locale=locale,
        trigger=trigger,
    )
    if sync_res.get("status") == "error":
        reason = sync_res.get("reason")
        logger.warning(
            "autorespond_exit",
            company_id=company_id,
            trigger=trigger,
            reason="negotiations_sync_failed",
            sync_reason=reason,
        )
        if progress and task_key:
            with contextlib.suppress(Exception):
                await progress.cancel_task(task_key)
        if progress_bot and pipeline_context is None:
            with contextlib.suppress(Exception):
                await progress_bot.session.close()
        return {"status": "negotiations_sync_failed", "reason": reason}

    if is_task_group_pipeline and progress and task_key:
        await progress.set_nested_step_state(task_key, "negotiations", "done")
    elif progress and task_key:
        await progress.set_step_state(task_key, "negotiations", "done")

    # Load + filter candidates (uses original gating rules).
    async with session_factory() as session:
        raw = await _load_candidates(session, company_id, vacancy_ids, task_started_at)

    await _regenerate_missing_compatibility_scores(
        session_factory,
        user_id=user.id,
        vacancies=raw,
        user_stack=user_stack,
        user_exp=user_exp,
    )

    kw_filter = (
        (company.keyword_filter or "")
        if company.keyword_check_enabled is not False
        else ""
    )
    allow_missing_compat = vacancy_ids is not None
    compat_rejected, keyword_rejected = _autorespond_filter_rejection_counts(
        raw,
        min_compat=company.autorespond_min_compat,
        company_keyword_filter=kw_filter,
        keyword_mode=company.autorespond_keyword_mode,
        allow_missing_compatibility_score=allow_missing_compat,
    )
    filtered = autorespond_logic.filter_vacancies_for_autorespond(
        raw,
        min_compat=company.autorespond_min_compat,
        company_keyword_filter=kw_filter,
        keyword_mode=company.autorespond_keyword_mode,
        allow_missing_compatibility_score=allow_missing_compat,
    )
    filtered.sort(key=lambda v: -v.id)
    capped = autorespond_logic.apply_max_cap(filtered, company.autorespond_max_per_run)

    # Daily rate limit at dispatch time: cap to remaining slots so the pump never has to
    # deal with mid-run rate-limit exits.
    remaining_slots = (
        remaining_ui_apply_slots_sync(user.id) if settings.hh_ui_apply_enabled else None
    )
    if remaining_slots is not None and remaining_slots == 0:
        if progress and task_key:
            with contextlib.suppress(Exception):
                if is_task_group_pipeline:
                    from src.services.autorespond_progress import (
                        finish_task_group_autorespond_progress,
                    )

                    await finish_task_group_autorespond_progress(
                        bot=progress_bot,
                        chat_id=int(user.telegram_id),
                        task_key=task_key,
                        locale=locale,
                        bar_index=progress_bar_index,
                        total=0,
                        shortage_note=get_text("autorespond-progress-rate-limited", locale),
                        applications_skipped=True,
                    )
                else:
                    await progress.finish_task(
                        task_key,
                        shortage_note=get_text("autorespond-progress-rate-limited", locale),
                        complete_bars=False,
                    )
        if progress_bot and pipeline_context is None:
            with contextlib.suppress(Exception):
                await progress_bot.session.close()
        logger.info(
            "autorespond_rate_limited_at_dispatch",
            company_id=company_id,
            user_id=user.id,
            hh_ui_apply_count_today=current_ui_apply_count_sync(user.id),
            hh_ui_apply_max_per_day=get_hh_ui_apply_max_per_day_effective(),
        )
        return {
            "status": "rate_limited",
            "queued": 0,
            "skipped": 0,
            "failed": 0,
            "employer_tests": 0,
            "trigger": trigger,
            "negotiations_sync": sync_res,
        }
    if remaining_slots is not None and len(capped) > remaining_slots:
        capped = capped[:remaining_slots]

    raw_compat_metrics = _compatibility_log_metrics(raw)
    filtered_compat_metrics = _compatibility_log_metrics(filtered)

    logger.info(
        "autorespond_selection_breakdown",
        company_id=company_id,
        trigger=trigger,
        user_id=user.id,
        vacancy_ids_requested=len(vacancy_ids) if vacancy_ids is not None else None,
        raw_loaded=len(raw),
        min_compat=company.autorespond_min_compat,
        keyword_mode=company.autorespond_keyword_mode,
        keyword_check_enabled=(company.keyword_check_enabled is not False),
        keyword_filter_chars=len(kw_filter.strip()),
        allow_missing_compatibility_score=allow_missing_compat,
        compat_rejected=compat_rejected,
        keyword_rejected=keyword_rejected,
        after_filter=len(filtered),
        max_per_run=company.autorespond_max_per_run,
        after_cap=len(capped),
        compatibility_avg_percent_raw=raw_compat_metrics["average_percent"],
        compatibility_missing_raw=raw_compat_metrics["missing_count"],
        compatibility_histogram_raw=raw_compat_metrics["histogram"],
        compatibility_avg_percent_filtered=filtered_compat_metrics["average_percent"],
        compatibility_missing_filtered=filtered_compat_metrics["missing_count"],
        compatibility_histogram_filtered=filtered_compat_metrics["histogram"],
        hh_ui_apply_enabled=settings.hh_ui_apply_enabled,
        cover_task_enabled=cover_task_enabled,
        remaining_ui_apply_slots=remaining_slots,
    )

    # Already-handled rows still tick the bar via the "skipped" branch in the pump.
    async with session_factory() as session:
        attempt_repo = HhApplicationAttemptRepository(session)
        already_handled: set[str] = set()
        if capped:
            already_handled = await attempt_repo.hh_vacancy_ids_with_success_or_employer_questions(
                user.id,
                hh_acc_id,
                [v.hh_vacancy_id for v in capped],
            )

    work_units, pre_skipped_autorespond = autorespond_logic.work_units_for_autorespond_progress(
        capped, already_handled
    )
    logger.info(
        "autorespond_progress_totals",
        company_id=company_id,
        trigger=trigger,
        user_id=user.id,
        after_cap=len(capped),
        work_units=work_units,
        pre_skipped_autorespond=pre_skipped_autorespond,
    )

    if progress and task_key and not is_task_group_pipeline:
        if work_units <= 0:
            with contextlib.suppress(Exception):
                await progress.set_step_state(task_key, "applications", "skipped")
                await progress.finish_task(task_key, complete_bars=False)
            if progress_bot and pipeline_context is None:
                with contextlib.suppress(Exception):
                    await progress_bot.session.close()
            return {
                "status": "ok",
                "queued": 0,
                "skipped": pre_skipped_autorespond,
                "failed": 0,
                "employer_tests": 0,
                "trigger": trigger,
                "negotiations_sync": sync_res,
            }
        await progress.update_bar(task_key, progress_bar_index, 0, work_units)
        await progress.set_step_state(task_key, "applications", "running")
        await progress.set_active_step_index(task_key, 1)
        await progress.update_footer(
            task_key,
            [get_text("autorespond-progress-failed", locale, count=0)],
        )
        await clear_autorespond_done_counter(user.telegram_id, task_key)
        await clear_autorespond_failed_counter(user.telegram_id, task_key)
        await clear_autorespond_employer_test_counter(user.telegram_id, task_key)
    elif is_task_group_pipeline and progress and task_key:
        if work_units <= 0:
            from src.services.autorespond_progress import finish_task_group_autorespond_progress

            with contextlib.suppress(Exception):
                await finish_task_group_autorespond_progress(
                    bot=progress_bot,
                    chat_id=int(user.telegram_id),
                    task_key=task_key,
                    locale=locale,
                    bar_index=progress_bar_index,
                    total=work_units,
                    applications_skipped=True,
                )
            return {
                "status": "ok",
                "queued": 0,
                "skipped": pre_skipped_autorespond,
                "failed": 0,
                "employer_tests": 0,
                "trigger": trigger,
                "negotiations_sync": sync_res,
            }
        await progress.update_bar(task_key, progress_bar_index, 0, work_units)
        await progress.set_nested_step_state(task_key, "applications", "running")
        await progress.set_nested_active_step_index(task_key, 1)
        await progress.update_footer(
            task_key,
            [get_text("autorespond-progress-failed", locale, count=0)],
        )
        await clear_autorespond_done_counter(user.telegram_id, task_key)
        await clear_autorespond_failed_counter(user.telegram_id, task_key)
        await clear_autorespond_employer_test_counter(user.telegram_id, task_key)

    if settings.hh_ui_apply_enabled and not cover_task_enabled:
        logger.warning(
            "autorespond_cover_letter_disabled",
            company_id=company_id,
            trigger=trigger,
            user_id=user.id,
        )
        return {
            "status": "cover_letter_disabled",
            "queued": 0,
            "skipped": pre_skipped_autorespond,
            "failed": 0,
            "employer_tests": 0,
            "trigger": trigger,
            "negotiations_sync": sync_res,
        }

    # Resolve resume_id per vacancy and seed Redis state.
    if not task_key or user.telegram_id <= 0:
        # Without a chat we cannot drive the bar; still applies happen synchronously via
        # the legacy HTTP path elsewhere, but the new pipeline requires task_key + chat_id.
        return {
            "status": "ok",
            "queued": 0,
            "skipped": pre_skipped_autorespond,
            "failed": 0,
            "employer_tests": 0,
            "trigger": trigger,
            "negotiations_sync": sync_res,
        }

    cover_ai_client = AIClient() if len(resume_items) > 1 else None
    ready_specs: list[dict] = []
    vacancy_ids_for_pregen: list[int] = []
    pre_skipped_ids: list[int] = []
    load_guard = get_system_load_guard()
    try:
        for idx, vac in enumerate(capped):
            if idx > 0 and idx % settings.autorespond_loop_progress_log_every == 0:
                await load_guard.wait_if_overloaded("autorespond_dispatch_resume_pick")
            if vac.hh_vacancy_id in already_handled or vac.needs_employer_questions:
                pre_skipped_ids.append(int(vac.id))
                continue
            resume_id = await _resolve_resume_for_autorespond_bounded(
                cover_ai_client,
                vac,
                resume_items,
                stored_autorespond_resume_id=company.autorespond_resume_id,
            )
            if not resume_id:
                continue
            url = normalize_hh_vacancy_url(vac.url, vac.hh_vacancy_id)
            ready_specs.append(
                {
                    "autoparsed_vacancy_id": int(vac.id),
                    "hh_vacancy_id": str(vac.hh_vacancy_id),
                    "resume_id": str(resume_id),
                    "vacancy_url": url,
                    "company_id": int(company_id),
                }
            )
            vacancy_ids_for_pregen.append(int(vac.id))
    finally:
        if cover_ai_client is not None:
            with contextlib.suppress(Exception):
                await close_ai_client(cover_ai_client)

    chat_id = int(user.telegram_id)
    ar_prog = {
        "task_key": task_key,
        "total": work_units,
        "locale": locale,
        "title": company.vacancy_title,
        "celery_task_id": celery_id,
        "bar_index": progress_bar_index,
        "finish_progress_task": not is_task_group_pipeline,
    }
    resume_envelope = hh_ui_batch_resume_payload(
        user_id=user.id,
        chat_id=chat_id,
        message_id=0,
        locale=locale,
        hh_linked_account_id=hh_acc_id,
        feed_session_id=0,
        cover_letter_style=cover_letter_style,
        cover_task_enabled=cover_task_enabled,
        silent_feed=True,
        autorespond_progress=ar_prog,
    )

    # Only touch pipeline state + pump when there is work to do; otherwise this is
    # a no-op run that should not leave Redis state for the recovery sweep.
    if ready_specs:
        save_pipeline_envelope(
            chat_id,
            task_key,
            {
                "resume_envelope": resume_envelope,
                "total_work_units": work_units,
                "company_id": company_id,
                "user_id": user.id,
            },
        )

        from src.worker.tasks.cover_letter import pregenerate_for_apply_task

        if cover_task_enabled:
            mark_pregen_pending(chat_id, task_key, vacancy_ids_for_pregen)
            for spec in ready_specs:
                pregenerate_for_apply_task.delay(
                    task_key=task_key,
                    chat_id=chat_id,
                    user_id=user.id,
                    autoparsed_vacancy_id=spec["autoparsed_vacancy_id"],
                    resume_id=spec["resume_id"],
                    cover_letter_style=cover_letter_style,
                    apply_spec=spec,
                )

        # Drop any leftover legacy tail/checkpoint state for this task_key.
        clear_hh_ui_batch_checkpoint_sync(chat_id, task_key)
        clear_hh_ui_resume_envelope_sync(chat_id, task_key)

    # Tick the bar once for every pre-skipped vacancy so done eventually == total.
    for _vid in pre_skipped_ids:
        await _tick_autorespond_bar_bounded(
            bot=progress_bot,
            chat_id=chat_id,
            task_key=task_key,
            total=work_units,
            locale=locale,
            footer_failed_line=None,
            title=company.vacancy_title,
            celery_task_id=celery_id,
            bar_index=progress_bar_index,
            finish_progress_task=not is_task_group_pipeline,
        )

    logger.info(
        "autorespond_dispatch_seeded",
        company_id=company_id,
        trigger=trigger,
        user_id=user.id,
        chat_id=chat_id,
        task_key=task_key,
        ready=len(ready_specs),
        pre_skipped=len(pre_skipped_ids),
        cover_task_enabled=cover_task_enabled,
    )

    if pipeline_context is None and progress_bot:
        with contextlib.suppress(Exception):
            await progress_bot.session.close()

    return {
        "status": "ok",
        "queued": len(ready_specs),
        "skipped": pre_skipped_autorespond,
        "failed": 0,
        "employer_tests": 0,
        "trigger": trigger,
        "negotiations_sync": sync_res,
    }


# ---------------------------------------------------------------------------
# Task-group / manual-pipeline orchestrator (unchanged contract)
# ---------------------------------------------------------------------------


async def _run_manual_autoparse_autorespond_pipeline_async(
    session_factory: async_sessionmaker[AsyncSession],
    task: HHBotTask,
    company_id: int,
    user_id: int,
    *,
    progress_task_key: str | None = None,
) -> dict:
    from src.core.i18n import get_text
    from src.repositories.autoparse import AutoparseCompanyRepository
    from src.repositories.user import UserRepository
    from src.services.progress_service import ProgressService, create_progress_redis
    from src.worker.tasks.autoparse import _run_autoparse_company_async

    bot = task.create_bot()
    celery_id = str(task.request.id or "")
    try:
        async with session_factory() as session:
            company_repo = AutoparseCompanyRepository(session)
            company = await company_repo.get_by_id(company_id)
            user_repo = UserRepository(session)
            user = await user_repo.get_by_id(user_id)
            if not company or not user or company.user_id != user_id or company.is_deleted:
                return {"status": "error", "reason": "invalid_company"}
            if not company.is_enabled:
                return {"status": "skipped", "company_id": company_id}
            locale = user.language_code or "ru"
            telegram_id = user.telegram_id or 0
            hh_linked_account_id = int(company.autorespond_hh_linked_account_id or 0)
        if telegram_id <= 0:
            return {"status": "error", "reason": "no_telegram"}

        pk = progress_task_key or f"pipeline:{company_id}:{celery_id}"
        redis = create_progress_redis()
        svc = ProgressService(bot, telegram_id, redis, locale)
        await svc.start_task(
            pk,
            get_text("progress-pipeline-manual-title", locale),
            [
                get_text("progress-bar-scraping", locale),
                get_text("progress-bar-ai", locale),
                get_text("progress-bar-autorespond", locale),
            ],
            celery_task_id=celery_id,
            initial_totals=[0, 0, 0],
            steps=[
                {
                    "id": "negotiations",
                    "label": get_text("progress-step-negotiations-sync", locale),
                    "state": "running",
                },
                {
                    "id": "autoparse",
                    "label": get_text("progress-step-autoparse-pipeline", locale),
                    "state": "pending",
                },
                {
                    "id": "applications",
                    "label": get_text("progress-step-autorespond-applications", locale),
                    "state": "pending",
                },
            ],
            active_step_index=0,
        )

        sync_res = await _run_negotiations_sync_with_retry(
            session_factory,
            task,
            user_id=user_id,
            hh_acc_id=hh_linked_account_id,
            company_id=company_id,
            telegram_id=telegram_id,
            locale=locale,
            trigger="manual_pipeline",
        )
        if sync_res.get("status") == "error":
            with contextlib.suppress(Exception):
                await svc.cancel_task(pk)
            return {
                "status": "negotiations_sync_failed",
                "reason": sync_res.get("reason"),
            }

        await svc.set_step_state(pk, "negotiations", "done")
        await svc.set_step_state(pk, "autoparse", "running")
        await svc.set_active_step_index(pk, 1)
        await svc.set_nested_steps(
            pk,
            [
                {
                    "id": "autoparse",
                    "label": get_text("progress-step-autoparse-pipeline", locale),
                    "state": "running",
                },
                {
                    "id": "applications",
                    "label": get_text("progress-step-autorespond-applications", locale),
                    "state": "pending",
                },
            ],
            active_index=0,
        )

        from src.services.autorespond_streaming import (
            StreamingAutorespondContext,
            StreamingAutorespondFeed,
        )

        stream_ctx = StreamingAutorespondContext(
            session_factory=session_factory,
            company_id=company_id,
            user_id=user_id,
            chat_id=telegram_id,
            task_key=pk,
            locale=locale,
            celery_task_id=celery_id,
            hh_linked_account_id=hh_linked_account_id,
            progress=svc,
            progress_bot=bot,
            bar_index=2,
            trigger="manual_pipeline",
            worker_task=task,
        )
        streaming_feed = StreamingAutorespondFeed(stream_ctx)
        await streaming_feed.bootstrap_pending_from_db()

        ap_res = await _run_autoparse_company_async(
            session_factory,
            task,
            company_id,
            None,
            pipeline_progress=(svc, pk, bot),
            streaming_autorespond=streaming_feed,
        )
        if ap_res.get("status") != "completed":
            with contextlib.suppress(Exception):
                await svc.cancel_task(pk)
            return ap_res

        await svc.set_step_state(pk, "autoparse", "done")
        await svc.set_nested_step_state(pk, "autoparse", "done")

        result = await streaming_feed.finalize()
        result["negotiations_sync"] = sync_res
        return result
    finally:
        with contextlib.suppress(Exception):
            await bot.session.close()


# ---------------------------------------------------------------------------
# Recovery sweep — runs every minute via Celery beat
# ---------------------------------------------------------------------------


def _is_pipeline_run_complete(chat_id: int, task_key: str) -> bool:
    """True when bar counter has converged: nothing in ready set and no pregens pending."""
    from src.services.autorespond_pipeline_state import pregen_pending_count

    return (
        ready_remaining_count(chat_id, task_key) == 0
        and pregen_pending_count(chat_id, task_key) == 0
    )


async def _recover_stalled_pipelines_async() -> dict:
    """Re-enqueue ``apply_pump_task`` for runs whose pump heartbeat has gone stale."""
    from src.services.autorespond_progress import is_autorespond_cancelled_sync
    from src.worker.tasks.hh_ui_apply import apply_pump_task

    grace = float(settings.autorespond_recover_stalled_pump_grace_seconds)
    healed = 0
    cleared = 0
    inspected = 0
    for chat_id, task_key in iter_active_pipeline_envelopes():
        inspected += 1
        envelope = load_pipeline_envelope(chat_id, task_key)
        if not envelope:
            continue
        if is_autorespond_cancelled_sync(chat_id, task_key):
            clear_all_pipeline_state(chat_id, task_key)
            cleared += 1
            continue
        if _is_pipeline_run_complete(chat_id, task_key):
            clear_all_pipeline_state(chat_id, task_key)
            cleared += 1
            continue
        if ready_remaining_count(chat_id, task_key) <= 0:
            continue
        if get_pump_lock_owner_sync(chat_id, task_key):
            continue
        resume_envelope = envelope.get("resume_envelope")
        if isinstance(resume_envelope, dict):
            ar = resume_envelope.get("autorespond_progress")
            if isinstance(ar, dict) and ar.get("streaming_autorespond"):
                from src.services.autorespond_pipeline_state import (
                    is_streaming_parse_complete,
                    mark_streaming_parse_complete,
                )
                from src.worker.tasks.hh_ui_apply import _streaming_parse_producer_dead

                if (
                    not is_streaming_parse_complete(chat_id, task_key)
                    and _streaming_parse_producer_dead(ar)
                ):
                    mark_streaming_parse_complete(chat_id, task_key)
                    logger.warning(
                        "autorespond_recover_streaming_parse_marked_complete_producer_dead",
                        chat_id=chat_id,
                        task_key=task_key,
                    )
        age = pump_heartbeat_age_seconds(chat_id, task_key)
        if age is not None and age <= grace:
            continue
        resume_envelope = envelope.get("resume_envelope")
        if not isinstance(resume_envelope, dict):
            logger.warning(
                "autorespond_recover_stalled_no_envelope",
                chat_id=chat_id,
                task_key=task_key,
            )
            continue
        logger.warning(
            "autorespond_recover_stalled_reenqueue_pump",
            chat_id=chat_id,
            task_key=task_key,
            heartbeat_age=age,
            ready=ready_remaining_count(chat_id, task_key),
        )
        apply_pump_task.delay(
            task_key=task_key,
            chat_id=chat_id,
            resume_envelope=resume_envelope,
        )
        healed += 1
    return {"status": "ok", "inspected": inspected, "healed": healed, "cleared": cleared}


# ---------------------------------------------------------------------------
# Celery tasks
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="autoparse.manual_pipeline_autorespond",
    soft_time_limit=settings.autoparse_run_company_soft_time_limit_seconds
    + settings.autoparse_run_company_soft_time_limit_seconds,
    time_limit=settings.autoparse_run_company_time_limit_seconds
    + settings.autoparse_run_company_time_limit_seconds,
)
def run_manual_autoparse_autorespond_pipeline(
    self: HHBotTask,
    company_id: int,
    user_id: int,
    progress_task_key: str | None = None,
) -> dict:
    return run_async(
        lambda sf: _run_manual_autoparse_autorespond_pipeline_async(
            sf,
            self,
            company_id,
            user_id,
            progress_task_key=progress_task_key,
        )
    )


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="autorespond.dispatch",
    soft_time_limit=300,
    time_limit=360,
    acks_late=True,
)
def dispatch_autorespond(
    self,
    company_id: int,
    vacancy_ids: list[int] | None = None,
    trigger: str = "manual",
    task_started_at_iso: str | None = None,
    progress_task_key: str | None = None,
) -> dict:
    ts = None
    if task_started_at_iso:
        try:
            ts = datetime.fromisoformat(task_started_at_iso)
        except ValueError:
            ts = None
    return run_async(
        lambda sf: _run_autorespond_async(
            sf,
            self,
            company_id,
            vacancy_ids,
            trigger,
            ts,
            progress_task_key=progress_task_key,
        )
    )


# Old name kept for callers / scheduled jobs still using ``autoparse.run_autorespond``.
@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="autoparse.run_autorespond",
    soft_time_limit=300,
    time_limit=360,
)
def run_autorespond_company(
    self,
    company_id: int,
    vacancy_ids: list[int] | None = None,
    trigger: str = "manual",
    task_started_at_iso: str | None = None,
    progress_task_key: str | None = None,
) -> dict:
    """Compat shim: delegates to the new dispatcher. Old code keeps its task name."""
    ts = None
    if task_started_at_iso:
        try:
            ts = datetime.fromisoformat(task_started_at_iso)
        except ValueError:
            ts = None
    return run_async(
        lambda sf: _run_autorespond_async(
            sf,
            self,
            company_id,
            vacancy_ids,
            trigger,
            ts,
            progress_task_key=progress_task_key,
        )
    )


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="autoparse.chain_autorespond_after_manual_parse",
    soft_time_limit=120,
    time_limit=150,
)
def run_autorespond_after_manual_parse(
    self,
    prev_result: dict | None,
    company_id: int,
    user_id: int,
) -> dict:
    if not isinstance(prev_result, dict):
        logger.info(
            "chain_autorespond_skipped",
            company_id=company_id,
            user_id=user_id,
            reason="bad_prev",
        )
        return {"status": "skipped", "reason": "bad_prev"}
    if prev_result.get("status") != "completed":
        logger.info(
            "chain_autorespond_skipped",
            company_id=company_id,
            user_id=user_id,
            autoparse_status=prev_result.get("status"),
        )
        return {
            "status": "skipped",
            "reason": "autoparse_not_completed",
            "autoparse": prev_result,
        }
    return run_async(
        lambda sf: _run_autorespond_after_manual_parse_async(sf, company_id, user_id)
    )


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="autorespond.recover_stalled",
    queue="celery",
    soft_time_limit=60,
    time_limit=90,
)
def recover_stalled_autorespond_pipelines(self) -> dict:
    return run_async(lambda _sf: _recover_stalled_pipelines_async())
