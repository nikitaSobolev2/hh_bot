"""Celery tasks for the autoparse feature."""

import contextlib
from datetime import UTC, datetime, timedelta

import redis

from src.config import settings
from src.core.i18n import get_text
from src.core.logging import get_logger
from src.worker.app import celery_app
from src.worker.base_task import HHBotTask
from src.worker.utils import run_async

logger = get_logger(__name__)

_DISPATCH_LOCK_KEY = "lock:autoparse:dispatch"
_RUN_LOCK_PREFIX = "lock:autoparse:run:"
# Safety-net TTL: released explicitly via finally; this guards against a crashed worker
_CONCURRENT_RUN_LOCK_TTL = 2 * 3600
_ANALYSIS_BATCH_SIZE = 5

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


@celery_app.task(bind=True, base=HHBotTask, name="autoparse.dispatch_all", max_retries=1)
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
    soft_time_limit=600,
    time_limit=660,
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_autoparse_company(self, company_id: int, notify_user_id: int | None = None) -> dict:
    return run_async(lambda sf: _run_autoparse_company_async(sf, self, company_id, notify_user_id))


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
):
    """Construct an AutoparsedVacancy ORM instance from a vacancy result dict."""
    from src.models.autoparse import AutoparsedVacancy

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
        raw_api_data=vac.get("raw_api_data"),
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
    existing = await vacancy_repo.get_by_hh_id(hh_id)
    if existing is not None:
        return vac, existing

    existing_parsed = await parsed_vacancy_repo.get_by_hh_id(hh_id)
    if existing_parsed is not None:
        vac = {
            **vac,
            "description": existing_parsed.description or "",
            "raw_skills": existing_parsed.raw_skills or [],
            "raw_api_data": existing_parsed.raw_api_data,
        }
    return vac, None


async def _run_autoparse_company_async(
    session_factory, task, company_id: int, notify_user_id: int | None = None
) -> dict:
    from src.models.autoparse import AutoparsedVacancy
    from src.repositories.app_settings import AppSettingRepository
    from src.repositories.autoparse import AutoparseCompanyRepository, AutoparsedVacancyRepository
    from src.repositories.parsing import ParsedVacancyRepository
    from src.repositories.user import UserRepository
    from src.repositories.work_experience import WorkExperienceRepository
    from src.services.ai.client import AIClient
    from src.services.parser.hh_parser_service import HHParserService
    from src.services.task_checkpoint import TaskCheckpointService, create_checkpoint_redis
    from src.worker.circuit_breaker import CircuitBreaker

    r = _redis_client()
    lock_key = f"{_RUN_LOCK_PREFIX}{company_id}"
    task_id = task.request.id

    acquired = r.eval(_ACQUIRE_LOCK_SCRIPT, 1, lock_key, task_id, str(_CONCURRENT_RUN_LOCK_TTL))
    if not acquired:
        logger.info("Autoparse company already running", company_id=company_id)
        return {"status": "locked", "company_id": company_id}

    _progress_bot = None
    progress = None
    task_key = f"autoparse:{company_id}"
    checkpoint_key = task_key
    cb = CircuitBreaker("autoparse")
    checkpoint = TaskCheckpointService(create_checkpoint_redis())
    try:
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
            target_count = int(await settings_repo.get_value("autoparse_target_count", default=50))

            user_repo = UserRepository(session)
            user = await user_repo.get_by_id(company.user_id)
            ap_settings = (user.autoparse_settings or {}) if user else {}

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
        results = await parser.parse_vacancies(
            company.search_url,
            company.keyword_filter,
            target_count,
            known_hh_ids=global_ids,
            on_vacancy_scraped=_on_vacancy_scraped,
        )

        user_stack, user_exp = _build_user_profile(ap_settings, work_experiences)
        ai_client = AIClient() if (user_stack or user_exp) else None

        total_to_analyze = (
            sum(1 for v in results if v["hh_vacancy_id"] not in known_ids) if ai_client else 0
        )

        restored = await checkpoint.load(checkpoint_key, task_id)
        analyzed_offset, original_total = restored if restored else (0, total_to_analyze)
        analyzed_count = analyzed_offset

        if progress and analyzed_count > 0:
            await progress.update_bar(task_key, 1, analyzed_count, original_total)

        from src.services.ai.prompts import VacancyCompatInput

        def _orm_to_vac_dict(orm) -> dict:
            return {
                "hh_vacancy_id": orm.hh_vacancy_id,
                "url": orm.url,
                "title": orm.title,
                "description": orm.description or "",
                "raw_skills": orm.raw_skills or [],
                "raw_api_data": orm.raw_api_data,
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
            }

        to_analyze: list[tuple[dict, VacancyCompatInput]] = []
        async with session_factory() as session:
            vacancy_repo = AutoparsedVacancyRepository(session)
            parsed_repo = ParsedVacancyRepository(session)

            for vac in results:
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
                            raw_api_data=existing.raw_api_data,
                        )
                        to_analyze.append((vac_dict, compat_input))
                        continue

                compat_input = VacancyCompatInput(
                    hh_vacancy_id=hh_id,
                    title=vac.get("title", ""),
                    skills=vac.get("raw_skills", []),
                    description=vac.get("description", ""),
                    raw_api_data=vac.get("raw_api_data"),
                )
                to_analyze.append((vac, compat_input))

        new_count = 0
        for batch_start in range(0, len(to_analyze), _ANALYSIS_BATCH_SIZE):
            batch = to_analyze[batch_start : batch_start + _ANALYSIS_BATCH_SIZE]
            vac_dicts = [item[0] for item in batch]
            compat_inputs = [item[1] for item in batch]

            analyses: dict = {}
            if ai_client:
                analyses = await ai_client.analyze_vacancies_batch(
                    compat_inputs,
                    user_tech_stack=user_stack,
                    user_work_experience=user_exp,
                )

            async with session_factory() as session:
                for vac_dict, compat_input in zip(vac_dicts, compat_inputs):
                    analysis = analyses.get(compat_input.hh_vacancy_id) if analyses else None
                    compat_score = analysis.compatibility_score if analysis else None
                    ai_summary = (analysis.summary or None) if analysis else None
                    ai_stack = (analysis.stack or None) if analysis else None

                    session.add(
                        _build_autoparsed_vacancy(
                            vac_dict, company_id, compat_score, ai_summary, ai_stack
                        )
                    )
                await session.commit()

            new_count += len(batch)
            if ai_client:
                analyzed_count += len(batch)
                await checkpoint.save(
                    checkpoint_key,
                    task_id,
                    analyzed=analyzed_count,
                    total=original_total,
                )
                if progress:
                    await progress.update_bar(task_key, 1, analyzed_count, original_total)

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
        return {"status": "completed", "new_count": new_count, "company_id": company_id}

    except Exception as exc:
        cb.record_failure()
        logger.error("Autoparse task failed", company_id=company_id, error=str(exc))
        raise
    finally:
        if progress:
            with contextlib.suppress(Exception):
                await progress.finish_task(task_key)
        r.delete(lock_key)
        if _progress_bot:
            await _progress_bot.session.close()


_DELIVER_TASK_PREFIX = "autoparse:deliver_task:"


@celery_app.task(bind=True, base=HHBotTask, name="autoparse.deliver_results", max_retries=3)
def deliver_autoparse_results(self, company_id: int, user_id: int, force_now: bool = False) -> dict:
    return run_async(lambda sf: _deliver_results_async(sf, self, company_id, user_id, force_now))


async def _deliver_results_async(
    session_factory, task, company_id: int, user_id: int, force_now: bool = False
) -> dict:
    from zoneinfo import ZoneInfo

    from src.repositories.autoparse import AutoparseCompanyRepository, AutoparsedVacancyRepository
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
            r = _redis_client()
            new_task = deliver_autoparse_results.apply_async(args=[company_id, user_id], eta=eta)
            r.set(f"{_DELIVER_TASK_PREFIX}{company_id}:{user_id}", new_task.id, ex=86400)
            return {"status": "rescheduled", "eta": str(eta)}

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

        # Exclude vacancies the user has already explicitly reviewed.
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

    if not new_vacancies:
        return {"status": "no_new_vacancies"}

    feed_session_id = await _create_feed_session(
        session_factory,
        user_id=user_id,
        company_id=company_id,
        chat_id=user.telegram_id,
        vacancy_ids=[v.id for v in new_vacancies],
    )

    await _send_feed_stats_card(
        bot_token=settings.bot_token,
        chat_id=user.telegram_id,
        vacancy_title=company.vacancy_title,
        vacancies=new_vacancies,
        feed_session_id=feed_session_id,
        locale=locale,
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


async def _create_feed_session(
    session_factory,
    user_id: int,
    company_id: int,
    chat_id: int,
    vacancy_ids: list[int],
) -> int:
    from src.repositories.vacancy_feed import VacancyFeedSessionRepository

    async with session_factory() as session:
        repo = VacancyFeedSessionRepository(session)
        feed_session = await repo.create(
            user_id=user_id,
            autoparse_company_id=company_id,
            chat_id=chat_id,
            vacancy_ids=vacancy_ids,
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
) -> None:
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.bot.modules.autoparse.callbacks import FeedCallback
    from src.bot.modules.autoparse.feed_services import build_stats_message

    compat_scores = [v.compatibility_score for v in vacancies if v.compatibility_score is not None]
    avg_compat = sum(compat_scores) / len(compat_scores) if compat_scores else None

    text = build_stats_message(vacancy_title, len(vacancies), avg_compat, locale)
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
