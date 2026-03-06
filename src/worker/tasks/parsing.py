"""Celery task for the full parsing pipeline."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.core.logging import get_logger
from src.worker.app import celery_app
from src.worker.utils import run_async

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    name="parsing.run_company",
    max_retries=2,
    default_retry_delay=30,
)
def run_parsing_company(
    self,
    parsing_company_id: int,
    user_id: int,
    include_blacklisted: bool = False,
) -> dict:
    return run_async(
        _run_parsing_company_async(self, parsing_company_id, user_id, include_blacklisted)
    )


async def _run_parsing_company_async(
    task,
    parsing_company_id: int,
    user_id: int,
    include_blacklisted: bool = False,
) -> dict:
    from src.db.engine import async_session_factory
    from src.models.blacklist import VacancyBlacklist
    from src.models.parsing import AggregatedResult, ParsedVacancy
    from src.repositories.app_settings import AppSettingRepository
    from src.repositories.blacklist import BlacklistRepository
    from src.repositories.parsing import ParsingCompanyRepository
    from src.repositories.task import CeleryTaskRepository
    from src.services.parser.extractor import ParsingExtractor
    from src.worker.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker("parsing")

    async with async_session_factory() as session:
        settings_repo = AppSettingRepository(session)

        enabled = await settings_repo.get_value("task_parsing_enabled", default=True)
        if not enabled:
            logger.warning("Parsing task disabled via settings")
            return {"status": "disabled"}

        cb_threshold = await settings_repo.get_value("cb_parsing_failure_threshold", default=5)
        cb_timeout = await settings_repo.get_value("cb_parsing_recovery_timeout", default=60)
        cb.update_config(failure_threshold=int(cb_threshold), recovery_timeout=int(cb_timeout))

    if not cb.is_call_allowed():
        logger.warning("Circuit breaker open for parsing")
        return {"status": "circuit_open"}

    # Idempotency check
    idempotency_key = f"parse_company:{parsing_company_id}"
    async with async_session_factory() as session:
        task_repo = CeleryTaskRepository(session)
        existing = await task_repo.get_by_idempotency_key(idempotency_key)
        if existing and existing.status == "completed":
            logger.info("Task already completed (idempotent)", key=idempotency_key)
            return {"status": "already_completed", "task_id": existing.id}

    try:
        async with async_session_factory() as session:
            company_repo = ParsingCompanyRepository(session)
            company = await company_repo.get_by_id(parsing_company_id)
            if not company:
                return {"status": "error", "message": "Company not found"}

            await company_repo.update(company, status="processing")
            await session.commit()

            blacklisted_ids: set[str] = set()
            if not include_blacklisted:
                bl_repo = BlacklistRepository(session)
                blacklisted_ids = await bl_repo.get_active_ids(
                    user_id,
                    company.vacancy_title,
                )

        extractor = ParsingExtractor()

        async def on_progress(current: int, total: int):
            async with async_session_factory() as s:
                repo = ParsingCompanyRepository(s)
                c = await repo.get_by_id(parsing_company_id)
                if c:
                    await repo.update(c, vacancies_processed=current)
                    await s.commit()

        result = await extractor.run_pipeline(
            search_url=company.search_url,
            keyword_filter=company.keyword_filter,
            target_count=company.target_count,
            blacklisted_ids=blacklisted_ids,
            on_vacancy_processed=on_progress,
        )

        async with async_session_factory() as session:
            company_repo = ParsingCompanyRepository(session)
            company = await company_repo.get_by_id(parsing_company_id)

            for vac_data in result["vacancies"]:
                vacancy = ParsedVacancy(
                    parsing_company_id=parsing_company_id,
                    hh_vacancy_id=vac_data["hh_vacancy_id"],
                    url=vac_data["url"],
                    title=vac_data["title"],
                    description=vac_data.get("description", ""),
                    raw_skills=vac_data.get("raw_skills"),
                    ai_keywords=vac_data.get("ai_keywords"),
                )
                session.add(vacancy)

            aggregated = AggregatedResult(
                parsing_company_id=parsing_company_id,
                top_keywords=result["keywords"],
                top_skills=result["skills"],
            )
            session.add(aggregated)

            if company:
                company.status = "completed"
                company.vacancies_processed = len(result["vacancies"])
                company.completed_at = datetime.now(UTC).replace(tzinfo=None)

            # Auto-blacklist (upsert to handle re-parsed vacancies)
            settings_repo = AppSettingRepository(session)
            bl_days = await settings_repo.get_value("blacklist_days", default=30)
            bl_until = (datetime.now(UTC) + timedelta(days=int(bl_days))).replace(tzinfo=None)
            vacancy_title = company.vacancy_title if company else ""

            for vac_data in result["vacancies"]:
                stmt = (
                    pg_insert(VacancyBlacklist)
                    .values(
                        user_id=user_id,
                        vacancy_title_context=vacancy_title,
                        hh_vacancy_id=vac_data["hh_vacancy_id"],
                        vacancy_url=vac_data["url"],
                        vacancy_name=vac_data["title"],
                        blacklisted_until=bl_until,
                    )
                    .on_conflict_do_update(
                        constraint="uq_user_vacancy_context",
                        set_={
                            "vacancy_url": vac_data["url"],
                            "vacancy_name": vac_data["title"],
                            "blacklisted_until": bl_until,
                        },
                    )
                )
                await session.execute(stmt)

            # Record task completion
            from src.models.task import BaseCeleryTask

            task_record = BaseCeleryTask(
                celery_task_id=task.request.id if task.request else None,
                task_type="parse_company",
                user_id=user_id,
                status="completed",
                idempotency_key=idempotency_key,
                result_data={"vacancies_count": len(result["vacancies"])},
            )
            session.add(task_record)

            await session.commit()

        cb.record_success()

        # Notify user via Telegram
        try:
            await _notify_user(user_id, parsing_company_id)
        except Exception as exc:
            logger.error("Failed to notify user", error=str(exc))

        return {
            "status": "completed",
            "vacancies_count": len(result["vacancies"]),
            "keywords_count": len(result["keywords"]),
            "skills_count": len(result["skills"]),
        }

    except Exception as exc:
        cb.record_failure()

        async with async_session_factory() as session:
            company_repo = ParsingCompanyRepository(session)
            company = await company_repo.get_by_id(parsing_company_id)
            if company:
                company.status = "failed"
                await session.commit()

            from src.models.task import BaseCeleryTask

            task_record = BaseCeleryTask(
                celery_task_id=task.request.id if task.request else None,
                task_type="parse_company",
                user_id=user_id,
                status="failed",
                idempotency_key=idempotency_key,
                error_message=str(exc),
            )
            session.add(task_record)
            await session.commit()

        logger.error("Parsing task failed", error=str(exc), company_id=parsing_company_id)
        raise


async def _notify_user(user_id: int, parsing_company_id: int) -> None:
    from src.bot.modules.parsing.keyboards import format_choice_keyboard
    from src.config import settings as app_settings
    from src.db.engine import async_session_factory
    from src.repositories.user import UserRepository

    async with async_session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_id(user_id)
        if not user:
            return

    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    bot = Bot(
        token=app_settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await bot.send_message(
            user.telegram_id,
            f"<b>✅ Parsing completed!</b>\n\n"
            f"Your parsing #{parsing_company_id} is ready.\n"
            f"Choose how to view the results:",
            reply_markup=format_choice_keyboard(parsing_company_id),
        )
    finally:
        await bot.session.close()
