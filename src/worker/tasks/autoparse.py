"""Celery tasks for the autoparse feature."""

import contextlib
from datetime import UTC, datetime, timedelta

import redis

from src.config import settings
from src.core.i18n import get_text
from src.core.logging import get_logger
from src.worker.app import celery_app
from src.worker.utils import run_async

logger = get_logger(__name__)

_DISPATCH_LOCK_KEY = "autoparse:dispatch_lock"
_RUN_LOCK_PREFIX = "autoparse:run:"
# Safety-net TTL: released explicitly via finally; this guards against a crashed worker
_CONCURRENT_RUN_LOCK_TTL = 2 * 3600


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url)


@celery_app.task(bind=True, name="autoparse.dispatch_all", max_retries=1)
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
    name="autoparse.run_company",
    max_retries=2,
    default_retry_delay=60,
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

    user_exp = (
        "\n".join(f"{e.company_name} — {e.stack}" for e in work_experiences)
        if work_experiences
        else ""
    )
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
    from src.worker.circuit_breaker import CircuitBreaker

    r = _redis_client()
    lock_key = f"{_RUN_LOCK_PREFIX}{company_id}"

    if not r.set(lock_key, "1", nx=True, ex=_CONCURRENT_RUN_LOCK_TTL):
        logger.info("Autoparse company already running", company_id=company_id)
        return {"status": "locked", "company_id": company_id}

    _progress_bot = None
    progress = None
    task_key = f"autoparse:{company_id}"
    cb = CircuitBreaker("autoparse")
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
        analyzed_count = 0
        new_count = 0
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
                        cached_compat = None
                        cached_summary = None
                        cached_stack = None
                        if ai_client:
                            analysis = await ai_client.analyze_vacancy(
                                vacancy_title=company.vacancy_title,
                                vacancy_skills=existing.raw_skills or [],
                                vacancy_description=existing.description or "",
                                user_tech_stack=user_stack,
                                user_work_experience=user_exp,
                            )
                            cached_compat = analysis.compatibility_score
                            cached_summary = analysis.summary or None
                            cached_stack = analysis.stack or None
                            analyzed_count += 1
                            if progress:
                                await progress.update_bar(
                                    task_key, 1, analyzed_count, total_to_analyze
                                )
                        session.add(
                            AutoparsedVacancy(
                                autoparse_company_id=company_id,
                                hh_vacancy_id=hh_id,
                                url=existing.url,
                                title=existing.title,
                                description=existing.description,
                                raw_skills=existing.raw_skills,
                                company_name=existing.company_name,
                                company_url=existing.company_url,
                                salary=existing.salary,
                                compensation_frequency=existing.compensation_frequency,
                                work_experience=existing.work_experience,
                                employment_type=existing.employment_type,
                                work_schedule=existing.work_schedule,
                                working_hours=existing.working_hours,
                                work_formats=existing.work_formats,
                                tags=existing.tags,
                                compatibility_score=cached_compat,
                                ai_summary=cached_summary,
                                ai_stack=cached_stack,
                            )
                        )
                        new_count += 1
                        continue

                compat_score = None
                ai_summary = None
                ai_stack = None
                if ai_client:
                    analysis = await ai_client.analyze_vacancy(
                        vacancy_title=company.vacancy_title,
                        vacancy_skills=vac.get("raw_skills", []),
                        vacancy_description=vac.get("description", ""),
                        user_tech_stack=user_stack,
                        user_work_experience=user_exp,
                    )
                    compat_score = analysis.compatibility_score
                    ai_summary = analysis.summary or None
                    ai_stack = analysis.stack or None
                    analyzed_count += 1
                    if progress:
                        await progress.update_bar(task_key, 1, analyzed_count, total_to_analyze)

                session.add(
                    _build_autoparsed_vacancy(vac, company_id, compat_score, ai_summary, ai_stack)
                )
                new_count += 1

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


@celery_app.task(bind=True, name="autoparse.deliver_results", max_retries=3)
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
        if not company:
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
