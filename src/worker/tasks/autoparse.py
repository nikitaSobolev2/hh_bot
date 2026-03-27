"""Celery tasks for the autoparse feature."""

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta

import httpx
import redis

from src.config import settings
from src.core.i18n import get_text
from src.core.logging import get_logger
from src.worker.app import celery_app
from src.worker.base_task import HHBotTask
from src.worker.hh_captcha_retry import celery_captcha_retry_countdown
from src.worker.utils import run_async

logger = get_logger(__name__)

_DISPATCH_LOCK_KEY = "lock:autoparse:dispatch"
_RUN_LOCK_PREFIX = "lock:autoparse:run:"
_ANALYSIS_BATCH_SIZE = 5

# Extend lock TTL while the same Celery task id still holds the key (sliding window).
_LOCK_RENEW_SCRIPT = """
local current = redis.call('GET', KEYS[1])
if current == false then return 0 end
if current == ARGV[1] then
  redis.call('EXPIRE', KEYS[1], ARGV[2])
  return 1
end
return 0
"""


def _autoparse_pipeline_batch_size() -> int:
    n = settings.hh_autoparse_pipeline_batch_size
    return n if n > 0 else settings.hh_vacancy_detail_concurrency

# Atomically acquire or re-acquire a task-owned lock.
# Returns 1 when the lock is taken (new or re-delivery of same task).
# Returns 0 when a *different* task already holds the lock.
_ACQUIRE_LOCK_SCRIPT = """
local current = redis.call('GET', KEYS[1])
if current == false or current == ARGV[1] then
    redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
    return 1
end
return 0
"""


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url)


_RELEASE_RUN_LOCK_SCRIPT = """
local current = redis.call('GET', KEYS[1])
if current == false then return 0 end
if current == ARGV[1] then
  redis.call('DEL', KEYS[1])
  return 1
end
return 0
"""


def _release_autoparse_run_lock_best_effort(company_id: int, celery_task_id: str) -> None:
    """Delete run lock only if still owned by this Celery task (e.g. soft time limit cleanup)."""
    r = _redis_client()
    key = f"{_RUN_LOCK_PREFIX}{company_id}"
    try:
        r.eval(_RELEASE_RUN_LOCK_SCRIPT, 1, key, celery_task_id)
    except Exception:
        logger.exception("Failed to release autoparse run lock", company_id=company_id)


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="autoparse.dispatch_all",
    max_retries=1,
    soft_time_limit=120,
    time_limit=180,
)
def dispatch_all_autoparse(self) -> dict:
    return run_async(lambda sf: _dispatch_all_async(sf))


async def _dispatch_all_async(session_factory) -> dict:
    from src.repositories.app_settings import AppSettingRepository
    from src.repositories.autoparse import AutoparseCompanyRepository

    r = _redis_client()
    if not r.set(_DISPATCH_LOCK_KEY, "1", nx=True, ex=300):
        logger.info("Autoparse dispatch already running (lock held)")
        return {"status": "locked"}

    try:
        async with session_factory() as session:
            settings_repo = AppSettingRepository(session)
            enabled = await settings_repo.get_value("task_autoparse_enabled", default=True)
            if not enabled:
                logger.warning("Autoparse dispatch disabled via settings")
                return {"status": "disabled"}

            interval = int(await settings_repo.get_value("autoparse_interval_hours", default=6))

            repo = AutoparseCompanyRepository(session)
            companies = await repo.get_due_for_dispatch(interval)

        dispatched = 0
        for company in companies:
            run_autoparse_company.delay(company.id)
            dispatched += 1

        logger.info("Autoparse dispatch completed", dispatched=dispatched)
        return {"status": "dispatched", "count": dispatched}
    finally:
        r.delete(_DISPATCH_LOCK_KEY)


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="autoparse.run_company",
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=settings.autoparse_run_company_soft_time_limit_seconds,
    time_limit=settings.autoparse_run_company_time_limit_seconds,
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_autoparse_company(self, company_id: int, notify_user_id: int | None = None) -> dict:
    from celery.exceptions import SoftTimeLimitExceeded

    from src.services.parser.scraper import HHCaptchaRequiredError

    try:
        return run_async(
            lambda sf: _run_autoparse_company_async(sf, self, company_id, notify_user_id)
        )
    except HHCaptchaRequiredError as exc:
        countdown = celery_captcha_retry_countdown(self)
        logger.warning(
            "Autoparse: HH captcha required; scheduling Celery retry",
            company_id=company_id,
            countdown=countdown,
        )
        raise self.retry(exc=exc, countdown=countdown) from exc
    except SoftTimeLimitExceeded:
        # Async finally usually runs; this is a fallback if the worker raised before coroutine cleanup.
        logger.warning(
            "Autoparse run company Celery soft time limit exceeded",
            company_id=company_id,
            soft_time_limit_seconds=settings.autoparse_run_company_soft_time_limit_seconds,
        )
        _release_autoparse_run_lock_best_effort(company_id, self.request.id)
        raise


def _build_user_profile(
    ap_settings: dict,
    work_experiences: list,
) -> tuple[list[str], str]:
    """Derive the user's tech stack and experience summary from settings and work history."""
    from src.bot.modules.autoparse.services import derive_tech_stack_from_experiences

    custom_stack = ap_settings.get("tech_stack", [])
    if custom_stack:
        user_stack = custom_stack
    elif work_experiences:
        user_stack = derive_tech_stack_from_experiences(work_experiences)
    else:
        user_stack = []

    from src.services.formatters import format_work_experience_block

    user_exp = format_work_experience_block(work_experiences) if work_experiences else ""
    return user_stack, user_exp


def _build_autoparsed_vacancy(
    vac: dict,
    company_id: int,
    compat_score: float | None,
    ai_summary: str | None = None,
    ai_stack: list[str] | None = None,
    employer_id: int | None = None,
    area_id: int | None = None,
):
    """Construct an AutoparsedVacancy ORM instance from a vacancy result dict."""
    from src.models.autoparse import AutoparsedVacancy

    of = vac.get("orm_fields") or {}
    return AutoparsedVacancy(
        autoparse_company_id=company_id,
        hh_vacancy_id=vac["hh_vacancy_id"],
        url=vac.get("url", ""),
        title=vac.get("title", ""),
        description=vac.get("description", ""),
        raw_skills=vac.get("raw_skills"),
        company_name=vac.get("company_name"),
        company_url=vac.get("company_url"),
        salary=vac.get("salary"),
        compensation_frequency=vac.get("compensation_frequency"),
        work_experience=vac.get("work_experience"),
        employment_type=vac.get("employment_type"),
        work_schedule=vac.get("work_schedule"),
        working_hours=vac.get("working_hours"),
        work_formats=vac.get("work_formats"),
        tags=vac.get("tags"),
        compatibility_score=compat_score,
        ai_summary=ai_summary or None,
        ai_stack=ai_stack or None,
        employer_id=employer_id,
        area_id=area_id,
        snippet_requirement=of.get("snippet_requirement"),
        snippet_responsibility=of.get("snippet_responsibility"),
        experience_id=of.get("experience_id"),
        experience_name=of.get("experience_name"),
        schedule_id=of.get("schedule_id"),
        schedule_name=of.get("schedule_name"),
        employment_id=of.get("employment_id"),
        employment_name=of.get("employment_name"),
        employment_form_id=of.get("employment_form_id"),
        employment_form_name=of.get("employment_form_name"),
        salary_from=of.get("salary_from"),
        salary_to=of.get("salary_to"),
        salary_currency=of.get("salary_currency"),
        salary_gross=of.get("salary_gross"),
        address_raw=of.get("address_raw"),
        address_city=of.get("address_city"),
        address_street=of.get("address_street"),
        address_building=of.get("address_building"),
        address_lat=of.get("address_lat"),
        address_lng=of.get("address_lng"),
        metro_stations=of.get("metro_stations"),
        vacancy_type_id=of.get("vacancy_type_id"),
        published_at=of.get("published_at"),
        work_format=of.get("work_format"),
        professional_roles=of.get("professional_roles"),
    )


async def _resolve_cached_vacancy(
    hh_id: str,
    vac: dict,
    vacancy_repo,
    parsed_vacancy_repo,
) -> tuple[dict, object | None]:
    """Return (enriched_vac, existing_autoparsed) for a cached vacancy.

    Tries AutoparsedVacancy first (full data). Falls back to ParsedVacancy
    to merge description and raw_skills onto the card-level dict so that
    AI compatibility scoring can still run even when the vacancy was only
    previously seen via the manual parsing feature.
    """
    existing = await vacancy_repo.get_by_hh_id_with_employer(hh_id)
    if existing is not None:
        return vac, existing

    existing_parsed = await parsed_vacancy_repo.get_by_hh_id_with_employer(hh_id)
    if existing_parsed is not None:
        from src.schemas.vacancy import build_vacancy_api_context_from_orm

        vac = {
            **vac,
            "description": existing_parsed.description or "",
            "raw_skills": existing_parsed.raw_skills or [],
            "vacancy_api_context": build_vacancy_api_context_from_orm(existing_parsed),
        }
    return vac, None


async def _run_autoparse_company_async(
    session_factory, task, company_id: int, notify_user_id: int | None = None
) -> dict:
    from src.repositories.app_settings import AppSettingRepository
    from src.repositories.autoparse import AutoparseCompanyRepository, AutoparsedVacancyRepository
    from src.repositories.parsing import ParsedVacancyRepository
    from src.repositories.user import UserRepository
    from src.repositories.work_experience import WorkExperienceRepository
    from src.services.ai.client import AIClient
    from src.services.parser.hh_parser_service import HHParserService
    from src.services.parser.scraper import HHCaptchaRequiredError
    from src.services.task_checkpoint import TaskCheckpointService, create_checkpoint_redis
    from src.worker.circuit_breaker import CircuitBreaker

    r = _redis_client()
    lock_key = f"{_RUN_LOCK_PREFIX}{company_id}"
    task_id = task.request.id

    lock_ttl = str(settings.autoparse_run_company_lock_ttl_seconds)
    acquired = r.eval(_ACQUIRE_LOCK_SCRIPT, 1, lock_key, task_id, lock_ttl)
    if not acquired:
        logger.info("Autoparse company already running", company_id=company_id)
        return {"status": "locked", "company_id": company_id}

    _progress_bot = None
    progress = None
    task_key = f"autoparse:{company_id}"
    checkpoint_key = task_key
    cb = CircuitBreaker("autoparse")
    checkpoint = TaskCheckpointService(create_checkpoint_redis())
    hb_task: asyncio.Task[None] | None = None
    try:

        async def _run_lock_heartbeat() -> None:
            """Sliding TTL on Redis run lock — covers long search + pipeline without a fixed wall clock."""
            interval = settings.autoparse_run_company_lock_renew_interval_seconds
            while True:
                await asyncio.sleep(interval)
                try:
                    await asyncio.to_thread(
                        r.eval,
                        _LOCK_RENEW_SCRIPT,
                        1,
                        lock_key,
                        task_id,
                        lock_ttl,
                    )
                except Exception as ex:
                    logger.warning(
                        "Autoparse run lock renew failed",
                        company_id=company_id,
                        error=str(ex),
                    )

        hb_task = asyncio.create_task(_run_lock_heartbeat())

        if notify_user_id is not None:
            from aiogram import Bot
            from aiogram.client.default import DefaultBotProperties
            from aiogram.enums import ParseMode

            _progress_bot = Bot(
                token=settings.bot_token,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            )
        if not cb.is_call_allowed():
            logger.warning("Circuit breaker open for autoparse")
            return {"status": "circuit_open"}

        async with session_factory() as session:
            company_repo = AutoparseCompanyRepository(session)
            company = await company_repo.get_by_id(company_id)
            if not company or company.is_deleted or not company.is_enabled:
                return {"status": "skipped", "company_id": company_id}

            vacancy_repo = AutoparsedVacancyRepository(session)
            known_ids = await vacancy_repo.get_known_hh_ids_for_company(company_id)

            global_ids = await vacancy_repo.get_all_known_hh_ids()
            parsed_repo = ParsedVacancyRepository(session)
            global_ids |= await parsed_repo.get_all_hh_ids()

            settings_repo = AppSettingRepository(session)
            user_repo = UserRepository(session)
            user = await user_repo.get_by_id(company.user_id)
            ap_settings = (user.autoparse_settings or {}) if user else {}
            _valid_target = {10, 30, 50, 5000}
            if user and user.is_admin and ap_settings.get("target_count") in _valid_target:
                target_count = ap_settings["target_count"]
            else:
                target_count = int(
                    await settings_repo.get_value("autoparse_target_count", default=50)
                )

            we_repo = WorkExperienceRepository(session)
            work_experiences = await we_repo.get_active_by_user(company.user_id)

        if _progress_bot and user:
            locale = user.language_code or "ru"
            from src.services.progress_service import ProgressService, create_progress_redis

            progress = ProgressService(
                _progress_bot, user.telegram_id, create_progress_redis(), locale
            )
            await progress.start_task(
                task_key=task_key,
                title=company.vacancy_title,
                bar_labels=[
                    get_text("progress-bar-scraping", locale),
                    get_text("progress-bar-ai", locale),
                ],
                celery_task_id=task.request.id,
            )

        async def _on_vacancy_scraped(current: int, total: int) -> None:
            if progress:
                await progress.update_bar(task_key, 0, current, total)

        parser = HHParserService()
        scraper = parser._scraper
        from src.services.parser.hh_parser_service import partition_collected_urls

        collected_urls = await scraper.collect_vacancy_urls(
            company.search_url,
            company.keyword_filter,
            target_count,
            known_ids_to_include=global_ids,
        )
        cached_results, to_fetch = partition_collected_urls(collected_urls, target_count, global_ids)

        user_stack, user_exp = _build_user_profile(ap_settings, work_experiences)
        ai_client = AIClient() if (user_stack or user_exp) else None

        total_to_analyze = (
            sum(1 for v in cached_results if v["hh_vacancy_id"] not in known_ids) + len(to_fetch)
            if ai_client
            else 0
        )

        if progress and total_to_analyze > 0:
            await progress.update_bar(task_key, 0, total_to_analyze, total_to_analyze)

        restored = await checkpoint.load(checkpoint_key, task_id)
        analyzed_offset, original_total = restored if restored else (0, total_to_analyze)
        analyzed_count = analyzed_offset

        if progress and analyzed_count > 0:
            await progress.update_bar(task_key, 1, analyzed_count, original_total)

        from src.services.ai.prompts import VacancyCompatInput

        def _orm_to_vac_dict(orm) -> dict:
            from src.schemas.vacancy import build_vacancy_api_context_from_orm

            of = {}
            if hasattr(orm, "snippet_requirement"):
                of = {
                    "snippet_requirement": orm.snippet_requirement,
                    "snippet_responsibility": orm.snippet_responsibility,
                    "experience_id": orm.experience_id,
                    "experience_name": orm.experience_name,
                    "schedule_id": orm.schedule_id,
                    "schedule_name": orm.schedule_name,
                    "employment_id": orm.employment_id,
                    "employment_name": orm.employment_name,
                    "employment_form_id": orm.employment_form_id,
                    "employment_form_name": orm.employment_form_name,
                    "salary_from": orm.salary_from,
                    "salary_to": orm.salary_to,
                    "salary_currency": orm.salary_currency,
                    "salary_gross": orm.salary_gross,
                    "address_raw": orm.address_raw,
                    "address_city": orm.address_city,
                    "address_street": orm.address_street,
                    "address_building": orm.address_building,
                    "address_lat": orm.address_lat,
                    "address_lng": orm.address_lng,
                    "metro_stations": orm.metro_stations,
                    "vacancy_type_id": orm.vacancy_type_id,
                    "published_at": orm.published_at,
                    "work_format": orm.work_format,
                    "professional_roles": orm.professional_roles,
                }
            return {
                "hh_vacancy_id": orm.hh_vacancy_id,
                "url": orm.url,
                "title": orm.title,
                "description": orm.description or "",
                "raw_skills": orm.raw_skills or [],
                "vacancy_api_context": build_vacancy_api_context_from_orm(orm),
                "company_name": orm.company_name,
                "company_url": orm.company_url,
                "salary": orm.salary,
                "compensation_frequency": orm.compensation_frequency,
                "work_experience": orm.work_experience,
                "employment_type": orm.employment_type,
                "work_schedule": orm.work_schedule,
                "working_hours": orm.working_hours,
                "work_formats": orm.work_formats,
                "tags": orm.tags,
                "employer_data": {},
                "area_data": {},
                "orm_fields": of,
                "_employer_id": orm.employer_id if hasattr(orm, "employer_id") else None,
                "_area_id": orm.area_id if hasattr(orm, "area_id") else None,
            }

        cached_pairs: list[tuple[dict, VacancyCompatInput]] = []
        async with session_factory() as session:
            vacancy_repo = AutoparsedVacancyRepository(session)
            parsed_repo = ParsedVacancyRepository(session)

            for vac in cached_results:
                hh_id = vac["hh_vacancy_id"]

                if hh_id in known_ids:
                    continue

                if vac.get("cached"):
                    vac, existing = await _resolve_cached_vacancy(
                        hh_id, vac, vacancy_repo, parsed_repo
                    )
                    if existing is not None:
                        vac_dict = _orm_to_vac_dict(existing)
                        compat_input = VacancyCompatInput(
                            hh_vacancy_id=existing.hh_vacancy_id,
                            title=existing.title or "",
                            skills=existing.raw_skills or [],
                            description=existing.description or "",
                            vacancy_api_context=vac_dict.get("vacancy_api_context"),
                        )
                        cached_pairs.append((vac_dict, compat_input))

        cursor = analyzed_offset
        pending: list[tuple[dict, VacancyCompatInput]] = []
        new_count = 0
        new_autorespond_vacancy_ids: list[int] = []

        async def process_ai_db_chunk(chunk: list[tuple[dict, VacancyCompatInput]]) -> None:
            nonlocal new_count, analyzed_count
            if not chunk:
                return
            vac_dicts = [item[0] for item in chunk]
            compat_inputs = [item[1] for item in chunk]

            analyses: dict = {}
            if ai_client:
                analyses = await ai_client.analyze_vacancies_batch(
                    compat_inputs,
                    user_tech_stack=user_stack,
                    user_work_experience=user_exp,
                )

            async with session_factory() as session:
                from src.repositories.hh import HHAreaRepository, HHEmployerRepository

                employer_repo = HHEmployerRepository(session)
                area_repo = HHAreaRepository(session)
                inserted: list = []
                for vac_dict, compat_input in zip(vac_dicts, compat_inputs, strict=True):
                    analysis = analyses.get(compat_input.hh_vacancy_id) if analyses else None
                    compat_score = analysis.compatibility_score if analysis else None
                    ai_summary = (analysis.summary or None) if analysis else None
                    ai_stack = (analysis.stack or None) if analysis else None

                    employer_id = vac_dict.get("_employer_id")
                    area_id = vac_dict.get("_area_id")
                    if employer_id is None or area_id is None:
                        employer_data = vac_dict.get("employer_data") or {}
                        area_data = vac_dict.get("area_data") or {}
                        if employer_id is None and employer_data.get("id"):
                            employer = await employer_repo.get_or_create_by_hh_id(employer_data)
                            employer_id = employer.id
                        if area_id is None and area_data.get("id"):
                            area = await area_repo.get_or_create_by_hh_id(area_data)
                            area_id = area.id

                    row = _build_autoparsed_vacancy(
                        vac_dict,
                        company_id,
                        compat_score,
                        ai_summary,
                        ai_stack,
                        employer_id=employer_id,
                        area_id=area_id,
                    )
                    session.add(row)
                    inserted.append(row)
                await session.commit()
                new_autorespond_vacancy_ids.extend(
                    int(r.id) for r in inserted if getattr(r, "id", None) is not None
                )

            new_count += len(chunk)
            if ai_client:
                analyzed_count += len(chunk)
                await checkpoint.save(
                    checkpoint_key,
                    task_id,
                    analyzed=analyzed_count,
                    total=original_total,
                )
                if progress:
                    await progress.update_bar(task_key, 1, analyzed_count, original_total)

        async def flush_pending(force: bool = False) -> None:
            nonlocal pending
            if force:
                while pending:
                    n = min(_ANALYSIS_BATCH_SIZE, len(pending))
                    chunk = pending[:n]
                    pending = pending[n:]
                    await process_ai_db_chunk(chunk)
            else:
                while len(pending) >= _ANALYSIS_BATCH_SIZE:
                    chunk = pending[:_ANALYSIS_BATCH_SIZE]
                    pending = pending[_ANALYSIS_BATCH_SIZE:]
                    await process_ai_db_chunk(chunk)

        for pair in cached_pairs:
            if cursor > 0:
                cursor -= 1
                continue
            pending.append(pair)
            await flush_pending(force=False)

        detail_done = 0
        pipeline_batch = _autoparse_pipeline_batch_size()
        sem = asyncio.Semaphore(settings.hh_vacancy_detail_concurrency)

        async with httpx.AsyncClient() as client:
            for batch_start in range(0, len(to_fetch), pipeline_batch):
                if settings.hh_autoparse_inter_batch_sleep_seconds > 0 and batch_start > 0:
                    await asyncio.sleep(settings.hh_autoparse_inter_batch_sleep_seconds)
                batch = to_fetch[batch_start : batch_start + pipeline_batch]
                batch_results = await parser.fetch_details_batch_slice(client, batch, sem)
                for i, merged in enumerate(batch_results):
                    if isinstance(merged, HHCaptchaRequiredError):
                        raise merged
                    if isinstance(merged, Exception):
                        logger.warning(
                            "Vacancy fetch failed",
                            vacancy=batch[i],
                            error=merged,
                        )
                        continue
                    if merged is None:
                        continue
                    detail_done += 1
                    await _on_vacancy_scraped(detail_done, target_count)
                    if cursor > 0:
                        cursor -= 1
                        continue
                    compat_input = VacancyCompatInput(
                        hh_vacancy_id=merged["hh_vacancy_id"],
                        title=merged.get("title", ""),
                        skills=merged.get("raw_skills", []),
                        description=merged.get("description", ""),
                        vacancy_api_context=merged.get("vacancy_api_context"),
                    )
                    pending.append((merged, compat_input))
                    await flush_pending(force=False)

        await flush_pending(force=True)

        async with session_factory() as session:
            company_repo = AutoparseCompanyRepository(session)
            company = await company_repo.get_by_id(company_id)
            if company:
                await company_repo.update(
                    company,
                    last_parsed_at=datetime.now(UTC).replace(tzinfo=None),
                    total_runs=company.total_runs + 1,
                    total_vacancies_found=company.total_vacancies_found + new_count,
                )
            await session.commit()

        await checkpoint.clear(checkpoint_key)
        cb.record_success()

        if new_count > 0 and user:
            deliver_autoparse_results.delay(company_id, user.id)

        if (
            notify_user_id is None
            and new_count > 0
            and user
        ):
            async with session_factory() as ar_session:
                ar_settings = AppSettingRepository(ar_session)
                if await ar_settings.get_value("task_autorespond_enabled", default=False):
                    ar_company_repo = AutoparseCompanyRepository(ar_session)
                    ar_co = await ar_company_repo.get_by_id(company_id)
                    if (
                        ar_co
                        and ar_co.autorespond_enabled
                        and ar_co.autorespond_hh_linked_account_id
                        and new_autorespond_vacancy_ids
                    ):
                        from src.repositories.hh_linked_account import HhLinkedAccountRepository
                        from src.services.ai.resume_selection import normalize_hh_resume_cache_items
                        from src.worker.tasks.autorespond import run_autorespond_company

                        ar_acc_repo = HhLinkedAccountRepository(ar_session)
                        ar_acc = await ar_acc_repo.get_by_id(ar_co.autorespond_hh_linked_account_id)
                        if ar_acc and normalize_hh_resume_cache_items(ar_acc.resume_list_cache):
                            run_autorespond_company.delay(
                                company_id,
                                vacancy_ids=new_autorespond_vacancy_ids,
                                trigger="scheduled",
                            )

        if notify_user_id is not None and user:
            await _send_run_completed_notification(
                bot_token=settings.bot_token,
                chat_id=user.telegram_id,
                new_count=new_count,
                locale=user.language_code or "ru",
            )

        logger.info(
            "Autoparse company completed",
            company_id=company_id,
            new_vacancies=new_count,
        )
        if progress:
            with contextlib.suppress(Exception):
                await progress.finish_task(task_key)
        return {"status": "completed", "new_count": new_count, "company_id": company_id}

    except HHCaptchaRequiredError:
        if progress:
            with contextlib.suppress(Exception):
                await progress.mark_retrying(task_key)
        raise
    except Exception as exc:
        cb.record_failure()
        logger.error("Autoparse task failed", company_id=company_id, error=str(exc))
        if progress:
            with contextlib.suppress(Exception):
                await progress.cancel_task(task_key)
        raise
    finally:
        if hb_task is not None:
            hb_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await hb_task
        r.delete(lock_key)
        if _progress_bot:
            await _progress_bot.session.close()


_DELIVER_TASK_PREFIX = "autoparse:deliver_task:"
_DELIVER_LOCK_PREFIX = "lock:autoparse:deliver:"
_DELIVER_LOCK_TTL_S = 600

_RELEASE_DELIVER_LOCK_SCRIPT = """
local current = redis.call('GET', KEYS[1])
if current == false then return 0 end
if current == ARGV[1] then
  redis.call('DEL', KEYS[1])
  return 1
end
return 0
"""


def _revoke_prior_scheduled_deliver(r: redis.Redis, deliver_task_key: str) -> None:
    """Revoke a previously ETA-scheduled deliver task so it cannot stack with the new one."""
    old_id = r.get(deliver_task_key)
    if not old_id:
        return
    try:
        celery_app.control.revoke(old_id, terminate=False)
    except Exception:
        logger.warning(
            "Failed to revoke prior scheduled deliver task",
            old_task_id=old_id,
            exc_info=True,
        )


def _acquire_deliver_lock(r: redis.Redis, lock_key: str, celery_task_id: str) -> bool:
    return bool(r.set(lock_key, celery_task_id, nx=True, ex=_DELIVER_LOCK_TTL_S))


def _release_deliver_lock(r: redis.Redis, lock_key: str, celery_task_id: str) -> None:
    try:
        r.eval(_RELEASE_DELIVER_LOCK_SCRIPT, 1, lock_key, celery_task_id)
    except Exception:
        logger.warning(
            "Failed to release autoparse deliver lock",
            lock_key=lock_key,
            exc_info=True,
        )


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="autoparse.update_compat_unseen",
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=1200,
    time_limit=1260,
    acks_late=True,
    reject_on_worker_lost=True,
)
def update_compatibility_unseen_vacancies(self, user_id: int) -> dict:
    return run_async(lambda sf: _update_compat_unseen_async(sf, self, user_id))


async def _update_compat_unseen_async(
    session_factory, task, user_id: int
) -> dict:
    from celery.exceptions import SoftTimeLimitExceeded

    from src.repositories.app_settings import AppSettingRepository
    from src.repositories.autoparse import AutoparsedVacancyRepository
    from src.repositories.user import UserRepository
    from src.repositories.vacancy_feed import VacancyFeedSessionRepository
    from src.repositories.work_experience import WorkExperienceRepository
    from src.schemas.vacancy import build_vacancy_api_context_from_orm
    from src.services.ai.client import AIClient
    from src.services.ai.prompts import VacancyCompatInput
    from src.worker.circuit_breaker import CircuitBreaker

    acquired = await task.acquire_user_task_lock(user_id, "update_compat_unseen", ttl=3600)
    if not acquired:
        logger.info("Update compat unseen already running", user_id=user_id)
        return {"status": "already_running", "user_id": user_id}

    try:
        async with session_factory() as session:
            settings_repo = AppSettingRepository(session)
            enabled = await settings_repo.get_value("task_autoparse_enabled", default=True)
            if not enabled:
                return {"status": "disabled"}

            user_repo = UserRepository(session)
            user = await user_repo.get_by_id(user_id)
            if not user:
                return {"status": "user_not_found"}

            ap_settings = (user.autoparse_settings or {}) if user.autoparse_settings else {}
            we_repo = WorkExperienceRepository(session)
            work_experiences = await we_repo.get_active_by_user(user_id)
            user_stack, user_exp = _build_user_profile(ap_settings, work_experiences)

            if not user_stack and not user_exp:
                return {"status": "no_tech_stack"}

            feed_repo = VacancyFeedSessionRepository(session)
            liked = await feed_repo.get_all_liked_vacancy_ids_for_user(user_id)
            disliked = await feed_repo.get_all_disliked_vacancy_ids_for_user(user_id)
            reacted_ids = liked | disliked

            vacancy_repo = AutoparsedVacancyRepository(session)
            vacancies = await vacancy_repo.get_unseen_for_user(user_id, reacted_ids)

        if not vacancies:
            return {"status": "no_vacancies", "updated_count": 0}

        cb = CircuitBreaker("autoparse")
        if not cb.is_call_allowed():
            return {"status": "circuit_open"}

        ai_client = AIClient()
        updated_count = 0

        try:
            for batch_start in range(0, len(vacancies), _ANALYSIS_BATCH_SIZE):
                batch = vacancies[batch_start : batch_start + _ANALYSIS_BATCH_SIZE]
                compat_inputs = [
                    VacancyCompatInput(
                        hh_vacancy_id=v.hh_vacancy_id,
                        title=v.title or "",
                        skills=v.raw_skills or [],
                        description=v.description or "",
                        vacancy_api_context=build_vacancy_api_context_from_orm(v),
                    )
                    for v in batch
                ]

                try:
                    analyses = await ai_client.analyze_vacancies_batch(
                        compat_inputs,
                        user_tech_stack=user_stack,
                        user_work_experience=user_exp,
                    )
                    cb.record_success()
                except Exception as exc:
                    cb.record_failure()
                    logger.error("Update compat batch failed", error=str(exc))
                    raise

                async with session_factory() as session:
                    vacancy_repo = AutoparsedVacancyRepository(session)
                    for vac, compat_input in zip(batch, compat_inputs, strict=True):
                        analysis = analyses.get(compat_input.hh_vacancy_id)
                        if analysis is None:
                            continue
                        existing = await vacancy_repo.get_by_id(vac.id)
                        if existing:
                            await vacancy_repo.update(
                                existing,
                                compatibility_score=analysis.compatibility_score,
                                ai_summary=analysis.summary or None,
                                ai_stack=analysis.stack or None,
                            )
                            updated_count += 1
                    await session.commit()

            if user:
                locale = user.language_code or "ru"
                from aiogram import Bot
                from aiogram.client.default import DefaultBotProperties
                from aiogram.enums import ParseMode

                bot = Bot(
                    token=settings.bot_token,
                    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
                )
                try:
                    await bot.send_message(
                        user.telegram_id,
                        get_text("autoparse-update-compat-completed", locale, count=updated_count),
                    )
                finally:
                    await bot.session.close()

        except SoftTimeLimitExceeded:
            if user:
                locale = user.language_code or "ru"
                from aiogram import Bot
                from aiogram.client.default import DefaultBotProperties
                from aiogram.enums import ParseMode

                bot = Bot(
                    token=settings.bot_token,
                    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
                )
                try:
                    await bot.send_message(
                        user.telegram_id,
                        get_text("autoparse-update-compat-timeout", locale, count=updated_count),
                    )
                finally:
                    await bot.session.close()
            raise

        logger.info(
            "Update compat unseen completed",
            user_id=user_id,
            updated_count=updated_count,
        )
        return {"status": "completed", "updated_count": updated_count}
    finally:
        await task.release_user_task_lock(user_id, "update_compat_unseen")


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="autoparse.deliver_results",
    max_retries=3,
    soft_time_limit=600,
    time_limit=660,
)
def deliver_autoparse_results(self, company_id: int, user_id: int, force_now: bool = False) -> dict:
    return run_async(lambda sf: _deliver_results_async(sf, self, company_id, user_id, force_now))


async def _deliver_results_async(
    session_factory, task, company_id: int, user_id: int, force_now: bool = False
) -> dict:
    from zoneinfo import ZoneInfo

    from src.repositories.autoparse import (
        AutoparseCompanyRepository,
        AutoparsedVacancyRepository,
        feed_vacancy_newest_first_key,
    )
    from src.repositories.user import UserRepository
    from src.repositories.vacancy_feed import VacancyFeedSessionRepository

    async with session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        if not user:
            return {"status": "user_not_found"}

        ap_settings = user.autoparse_settings or {}
        send_time_str = ap_settings.get("send_time", "12:00")
        user_tz = ZoneInfo(user.timezone or "Europe/Moscow")
        now_user = datetime.now(user_tz)

        try:
            hour, minute = map(int, send_time_str.split(":"))
        except (ValueError, AttributeError):
            hour, minute = 12, 0

        target_time = now_user.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # Grace period so Celery ETA tasks arriving seconds after the
        # target are not incorrectly pushed to tomorrow.
        eta_grace = timedelta(minutes=2)
        if target_time + eta_grace < now_user:
            target_time += timedelta(days=1)

        diff_minutes = abs((now_user - target_time).total_seconds()) / 60
        if not force_now and diff_minutes > 30:
            eta = target_time.astimezone(UTC).replace(tzinfo=None)
            deliver_task_key = f"{_DELIVER_TASK_PREFIX}{company_id}:{user_id}"
            r_sched = _redis_client()
            try:
                _revoke_prior_scheduled_deliver(r_sched, deliver_task_key)
                new_task = deliver_autoparse_results.apply_async(
                    args=[company_id, user_id],
                    eta=eta,
                )
                r_sched.set(deliver_task_key, new_task.id, ex=86400)
            finally:
                r_sched.close()
            return {"status": "rescheduled", "eta": str(eta)}

    r = _redis_client()
    lock_key = f"{_DELIVER_LOCK_PREFIX}{company_id}:{user_id}"
    celery_task_id = str(task.request.id or "")
    try:
        if not _acquire_deliver_lock(r, lock_key, celery_task_id):
            logger.info(
                "autoparse_deliver_skipped_concurrent",
                company_id=company_id,
                user_id=user_id,
            )
            return {"status": "skipped_concurrent_deliver"}
        try:
            async with session_factory() as session:
                user_repo = UserRepository(session)
                user = await user_repo.get_by_id(user_id)
                if not user:
                    return {"status": "user_not_found"}

                ap_settings = user.autoparse_settings or {}
                locale = user.language_code or "ru"

                company_repo = AutoparseCompanyRepository(session)
                company = await company_repo.get_by_id(company_id)
                if not company or company.is_deleted:
                    return {"status": "company_not_found"}

                vacancy_repo = AutoparsedVacancyRepository(session)
                since = company.last_delivered_at or (
                    datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
                )
                min_compat = ap_settings.get("min_compatibility_percent", 50)
                new_vacancies = await vacancy_repo.get_new_since(company_id, since, min_compat)

                feed_repo = VacancyFeedSessionRepository(session)
                reacted_ids = await feed_repo.get_all_reacted_vacancy_ids(user_id, company_id)
                queued_ids = await feed_repo.get_all_seen_vacancy_ids(user_id, company_id)

                # Always exclude vacancies the user has already liked or disliked.
                # include_reacted_in_feed may later control re-parsing; feed never re-shows reacted.
                new_vacancies = [v for v in new_vacancies if v.id not in reacted_ids]

                # Also re-surface vacancies that were queued in a previous session but
                # never reached because the user stopped early.
                unreviewed_ids = queued_ids - reacted_ids
                if unreviewed_ids:
                    unreviewed = await vacancy_repo.get_by_ids(list(unreviewed_ids), min_compat)
                    already_included = {v.id for v in new_vacancies}
                    for v in unreviewed:
                        if v.id not in already_included:
                            new_vacancies.append(v)

                # Newest on HH first (published_at); missing date falls back to id.
                new_vacancies.sort(key=feed_vacancy_newest_first_key)

            if not new_vacancies:
                return {"status": "no_new_vacancies"}

            from src.services.hh.feed_gating import HhFeedAccountStatus, classify_user_hh_accounts

            async with session_factory() as session:
                hh_status, hh_accounts = await classify_user_hh_accounts(session, user_id)

            hh_linked_id: int | None = (
                hh_accounts[0].id if hh_status == HhFeedAccountStatus.SINGLE else None
            )

            feed_session_id = await _create_feed_session(
                session_factory,
                user_id=user_id,
                company_id=company_id,
                chat_id=user.telegram_id,
                vacancy_ids=[v.id for v in new_vacancies],
                hh_linked_account_id=hh_linked_id,
            )

            await _send_feed_stats_card(
                bot_token=settings.bot_token,
                chat_id=user.telegram_id,
                vacancy_title=company.vacancy_title,
                vacancies=new_vacancies,
                feed_session_id=feed_session_id,
                locale=locale,
                linked_accounts=hh_accounts,
            )

            async with session_factory() as session:
                company_repo = AutoparseCompanyRepository(session)
                refreshed = await company_repo.get_by_id(company_id)
                if refreshed:
                    await company_repo.update(
                        refreshed,
                        last_delivered_at=datetime.now(UTC).replace(tzinfo=None),
                    )

            return {"status": "delivered", "count": len(new_vacancies)}
        finally:
            _release_deliver_lock(r, lock_key, celery_task_id)
    finally:
        r.close()


async def _create_feed_session(
    session_factory,
    user_id: int,
    company_id: int,
    chat_id: int,
    vacancy_ids: list[int],
    *,
    hh_linked_account_id: int | None = None,
) -> int:
    from src.repositories.vacancy_feed import VacancyFeedSessionRepository

    async with session_factory() as session:
        repo = VacancyFeedSessionRepository(session)
        feed_session = await repo.create(
            user_id=user_id,
            autoparse_company_id=company_id,
            chat_id=chat_id,
            vacancy_ids=vacancy_ids,
            hh_linked_account_id=hh_linked_account_id,
            current_index=0,
            liked_ids=[],
            disliked_ids=[],
            is_completed=False,
        )
        await session.commit()
        return feed_session.id


async def _send_feed_stats_card(
    bot_token: str,
    chat_id: int,
    vacancy_title: str,
    vacancies: list,
    feed_session_id: int,
    locale: str,
    *,
    linked_accounts: list | None = None,
) -> None:
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.bot.modules.autoparse.callbacks import AutoparseCallback, FeedCallback
    from src.bot.modules.autoparse.feed_services import build_stats_message

    compat_scores = [v.compatibility_score for v in vacancies if v.compatibility_score is not None]
    avg_compat = sum(compat_scores) / len(compat_scores) if compat_scores else None

    text = build_stats_message(vacancy_title, len(vacancies), avg_compat, locale)
    linked_accounts = linked_accounts or []
    if len(linked_accounts) > 1:
        text = f"{text}\n\n{get_text('feed-pick-hh-hint', locale)}"
        rows: list[list[InlineKeyboardButton]] = []
        for acc in linked_accounts:
            label = (acc.label or acc.hh_user_id)[:40]
            rows.append(
                [
                    InlineKeyboardButton(
                        text=label,
                        callback_data=FeedCallback(
                            action="pick_hh_account",
                            session_id=feed_session_id,
                            hh_account_id=acc.id,
                        ).pack(),
                    )
                ]
            )
        rows.append(
            [
                InlineKeyboardButton(
                    text=get_text("btn-back", locale),
                    callback_data=AutoparseCallback(action="hub").pack(),
                )
            ]
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    else:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=get_text("feed-btn-start", locale),
                        callback_data=FeedCallback(action="start", session_id=feed_session_id).pack(),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=get_text("feed-btn-stop", locale),
                        callback_data=FeedCallback(action="stop", session_id=feed_session_id).pack(),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=get_text("btn-back", locale),
                        callback_data=AutoparseCallback(action="hub").pack(),
                    )
                ],
            ]
        )

    bot = Bot(
        token=bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    finally:
        await bot.session.close()


async def _send_run_completed_notification(
    bot_token: str,
    chat_id: int,
    new_count: int,
    locale: str,
) -> None:
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    if new_count > 0:
        text = get_text("autoparse-run-finished", locale, count=new_count)
    else:
        text = get_text("autoparse-run-finished-empty", locale)

    bot = Bot(
        token=bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    finally:
        await bot.session.close()
