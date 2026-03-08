"""Celery task for the full parsing pipeline."""

from datetime import UTC, datetime, timedelta
from functools import partial

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
        lambda sf: _run_parsing_company_async(
            sf, self, parsing_company_id, user_id, include_blacklisted,
        )
    )


async def _run_parsing_company_async(
    session_factory: async_sessionmaker[AsyncSession],
    task,
    parsing_company_id: int,
    user_id: int,
    include_blacklisted: bool = False,
) -> dict:
    from src.repositories.app_settings import AppSettingRepository
    from src.repositories.blacklist import BlacklistRepository
    from src.repositories.parsing import ParsingCompanyRepository
    from src.repositories.task import CeleryTaskRepository
    from src.services.parser.extractor import ParsingExtractor
    from src.worker.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker("parsing")

    async with session_factory() as session:
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

    idempotency_key = f"parse_company:{parsing_company_id}"
    async with session_factory() as session:
        task_repo = CeleryTaskRepository(session)
        existing = await task_repo.get_by_idempotency_key(idempotency_key)
        if existing and existing.status == "completed":
            logger.info("Task already completed (idempotent)", key=idempotency_key)
            return {"status": "already_completed", "task_id": existing.id}

    try:
        async with session_factory() as session:
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
        result = await extractor.run_pipeline(
            search_url=company.search_url,
            keyword_filter=company.keyword_filter,
            target_count=company.target_count,
            blacklisted_ids=blacklisted_ids,
            on_vacancy_processed=partial(
                _report_progress, session_factory, parsing_company_id,
            ),
        )

        await _save_parsing_results(
            session_factory,
            parsing_company_id,
            user_id,
            task,
            result,
            idempotency_key,
        )
        cb.record_success()

        try:
            await _notify_user(session_factory, user_id, parsing_company_id)
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
        await _mark_parsing_failed(
            session_factory,
            parsing_company_id,
            user_id,
            task,
            idempotency_key,
            exc,
        )
        logger.error("Parsing task failed", error=str(exc), company_id=parsing_company_id)
        raise


async def _report_progress(
    session_factory: async_sessionmaker[AsyncSession],
    parsing_company_id: int,
    current: int,
    _total: int,
) -> None:
    from src.repositories.parsing import ParsingCompanyRepository

    async with session_factory() as session:
        repo = ParsingCompanyRepository(session)
        company = await repo.get_by_id(parsing_company_id)
        if company:
            await repo.update(company, vacancies_processed=current)
            await session.commit()


async def _save_parsing_results(
    session_factory: async_sessionmaker[AsyncSession],
    parsing_company_id: int,
    user_id: int,
    task,
    result: dict,
    idempotency_key: str,
) -> None:
    from src.models.blacklist import VacancyBlacklist
    from src.models.parsing import AggregatedResult, ParsedVacancy
    from src.models.task import BaseCeleryTask
    from src.repositories.app_settings import AppSettingRepository
    from src.repositories.parsing import ParsingCompanyRepository

    async with session_factory() as session:
        company_repo = ParsingCompanyRepository(session)
        company = await company_repo.get_by_id(parsing_company_id)

        for vac_data in result["vacancies"]:
            session.add(
                ParsedVacancy(
                    parsing_company_id=parsing_company_id,
                    hh_vacancy_id=vac_data["hh_vacancy_id"],
                    url=vac_data["url"],
                    title=vac_data["title"],
                    description=vac_data.get("description", ""),
                    raw_skills=vac_data.get("raw_skills"),
                    ai_keywords=vac_data.get("ai_keywords"),
                )
            )

        session.add(
            AggregatedResult(
                parsing_company_id=parsing_company_id,
                top_keywords=result["keywords"],
                top_skills=result["skills"],
            )
        )

        if company:
            company.status = "completed"
            company.vacancies_processed = len(result["vacancies"])
            company.completed_at = datetime.now(UTC).replace(tzinfo=None)

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

        session.add(
            BaseCeleryTask(
                celery_task_id=task.request.id if task.request else None,
                task_type="parse_company",
                user_id=user_id,
                status="completed",
                idempotency_key=idempotency_key,
                result_data={"vacancies_count": len(result["vacancies"])},
            )
        )

        await session.commit()


async def _mark_parsing_failed(
    session_factory: async_sessionmaker[AsyncSession],
    parsing_company_id: int,
    user_id: int,
    task,
    idempotency_key: str,
    exc: Exception,
) -> None:
    from src.models.task import BaseCeleryTask
    from src.repositories.parsing import ParsingCompanyRepository

    async with session_factory() as session:
        company_repo = ParsingCompanyRepository(session)
        company = await company_repo.get_by_id(parsing_company_id)
        if company:
            company.status = "failed"
            await session.commit()

        session.add(
            BaseCeleryTask(
                celery_task_id=task.request.id if task.request else None,
                task_type="parse_company",
                user_id=user_id,
                status="failed",
                idempotency_key=idempotency_key,
                error_message=str(exc),
            )
        )
        await session.commit()


async def _notify_user(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: int,
    parsing_company_id: int,
) -> None:
    from src.config import settings as app_settings
    from src.core.i18n import get_text
    from src.repositories.user import UserRepository

    async with session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_id(user_id)
        if not user:
            return

    locale = user.language_code or "ru"

    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    from src.bot.modules.parsing.keyboards import format_choice_keyboard

    from src.services.ai.streaming import _send_with_retry

    bot = Bot(
        token=app_settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        text = get_text("parsing-completed", locale, id=str(parsing_company_id))
        kb = format_choice_keyboard(parsing_company_id, locale=locale)
        await _send_with_retry(
            bot, user.telegram_id, text=text, parse_mode="HTML", reply_markup=kb,
        )
    finally:
        await bot.session.close()
