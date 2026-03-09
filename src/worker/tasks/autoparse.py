"""Celery tasks for the autoparse feature."""

from datetime import UTC, datetime, timedelta

import redis

from src.config import settings
from src.core.logging import get_logger
from src.worker.app import celery_app
from src.worker.utils import run_async

logger = get_logger(__name__)

_DISPATCH_LOCK_KEY = "autoparse:dispatch_lock"
_RUN_LOCK_PREFIX = "autoparse:run:"


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

            repo = AutoparseCompanyRepository(session)
            companies = await repo.get_all_enabled()

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
def run_autoparse_company(self, company_id: int) -> dict:
    return run_async(lambda sf: _run_autoparse_company_async(sf, self, company_id))


async def _run_autoparse_company_async(session_factory, task, company_id: int) -> dict:
    from src.bot.modules.autoparse.services import derive_tech_stack_from_experiences
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

    async with session_factory() as session:
        settings_repo = AppSettingRepository(session)
        interval = await settings_repo.get_value("autoparse_interval_hours", default=6)

    lock_ttl = int(interval) * 3600
    if not r.set(lock_key, "1", nx=True, ex=lock_ttl):
        logger.info("Autoparse company already running", company_id=company_id)
        return {"status": "locked", "company_id": company_id}

    cb = CircuitBreaker("autoparse")
    if not cb.is_call_allowed():
        logger.warning("Circuit breaker open for autoparse")
        r.delete(lock_key)
        return {"status": "circuit_open"}

    try:
        async with session_factory() as session:
            company_repo = AutoparseCompanyRepository(session)
            company = await company_repo.get_by_id(company_id)
            if not company or company.is_deleted or not company.is_enabled:
                return {"status": "skipped", "company_id": company_id}

            vacancy_repo = AutoparsedVacancyRepository(session)
            known_ids = await vacancy_repo.get_known_hh_ids_for_company(company_id)

            global_ids = await vacancy_repo.get_all_known_hh_ids()
            parsed_repo = ParsedVacancyRepository(session)
            for row in await parsed_repo.get_all():
                global_ids.add(row.hh_vacancy_id)

            settings_repo = AppSettingRepository(session)
            target_count = int(await settings_repo.get_value("autoparse_target_count", default=50))

            user_repo = UserRepository(session)
            user = await user_repo.get_by_id(company.user_id)
            ap_settings = (user.autoparse_settings or {}) if user else {}

            we_repo = WorkExperienceRepository(session)
            work_experiences = await we_repo.get_active_by_user(company.user_id)

        parser = HHParserService()
        results = await parser.parse_vacancies(
            company.search_url,
            company.keyword_filter,
            target_count,
            known_hh_ids=global_ids,
        )

        custom_stack = ap_settings.get("tech_stack", [])
        if custom_stack:
            user_stack = custom_stack
        elif work_experiences:
            user_stack = derive_tech_stack_from_experiences(work_experiences)
        else:
            user_stack = []

        if work_experiences:
            user_exp = "\n".join(
                f"{e.company_name} — {e.stack}" for e in work_experiences
            )
        else:
            user_exp = ""

        has_profile = bool(user_stack or user_exp)
        ai_client = AIClient() if has_profile else None

        new_count = 0
        async with session_factory() as session:
            vacancy_repo = AutoparsedVacancyRepository(session)

            for vac in results:
                hh_id = vac["hh_vacancy_id"]

                if hh_id in known_ids:
                    continue

                if vac.get("cached"):
                    existing = await vacancy_repo.get_by_hh_id(hh_id)
                    if existing:
                        cached_compat = None
                        if ai_client and existing.raw_skills:
                            cached_compat = await ai_client.calculate_compatibility(
                                vacancy_title=company.vacancy_title,
                                vacancy_skills=existing.raw_skills,
                                vacancy_description=existing.description or "",
                                user_tech_stack=user_stack,
                                user_work_experience=user_exp,
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
                            )
                        )
                        new_count += 1
                        continue

                compat_score = None
                if ai_client and vac.get("raw_skills"):
                    compat_score = await ai_client.calculate_compatibility(
                        vacancy_title=company.vacancy_title,
                        vacancy_skills=vac.get("raw_skills", []),
                        vacancy_description=vac.get("description", ""),
                        user_tech_stack=user_stack,
                        user_work_experience=user_exp,
                    )

                session.add(
                    AutoparsedVacancy(
                        autoparse_company_id=company_id,
                        hh_vacancy_id=hh_id,
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
                    )
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


@celery_app.task(bind=True, name="autoparse.deliver_results", max_retries=3)
def deliver_autoparse_results(self, company_id: int, user_id: int) -> dict:
    return run_async(lambda sf: _deliver_results_async(sf, self, company_id, user_id))


async def _deliver_results_async(session_factory, task, company_id: int, user_id: int) -> dict:
    from zoneinfo import ZoneInfo

    from src.repositories.autoparse import AutoparseCompanyRepository, AutoparsedVacancyRepository
    from src.repositories.user import UserRepository

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
        if diff_minutes > 30:
            eta = target_time.astimezone(UTC).replace(tzinfo=None)
            deliver_autoparse_results.apply_async(args=[company_id, user_id], eta=eta)
            return {"status": "rescheduled", "eta": str(eta)}

        company_repo = AutoparseCompanyRepository(session)
        company = await company_repo.get_by_id(company_id)
        if not company:
            return {"status": "company_not_found"}

        vacancy_repo = AutoparsedVacancyRepository(session)
        today = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
        vacancies = await vacancy_repo.get_by_company(company_id, limit=100)
        new_vacancies = [v for v in vacancies if v.created_at >= today]

    if not new_vacancies:
        return {"status": "no_new_vacancies"}

    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    try:
        lines = [f"<b>\U0001f4e5 {company.vacancy_title}</b>\n"]
        for v in new_vacancies[:20]:
            compat = f" [{v.compatibility_score:.0f}%]" if v.compatibility_score is not None else ""
            salary = f" | {v.salary}" if v.salary else ""
            lines.append(
                f"\u2022 <a href='{v.url}'>{v.title}</a>{salary}{compat}"
                f"\n  {v.company_name or '—'}"
                f" | {v.work_formats or '—'}"
            )
        if len(new_vacancies) > 20:
            lines.append(f"\n... and {len(new_vacancies) - 20} more")

        text = "\n".join(lines)
        from src.services.ai.streaming import _send_with_retry

        await _send_with_retry(bot, user.telegram_id, text=text, parse_mode="HTML")
    finally:
        await bot.session.close()

    return {"status": "delivered", "count": len(new_vacancies)}
