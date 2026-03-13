"""Celery task for the full parsing pipeline."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

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
    telegram_chat_id: int = 0,
) -> dict:
    return run_async(
        lambda sf: _run_parsing_company_async(
            sf,
            self,
            parsing_company_id,
            user_id,
            include_blacklisted,
            telegram_chat_id,
        )
    )


async def _run_parsing_company_async(
    session_factory: async_sessionmaker[AsyncSession],
    task,
    parsing_company_id: int,
    user_id: int,
    include_blacklisted: bool = False,
    telegram_chat_id: int = 0,
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

    bot, locale = await _init_bot_and_locale(
        session_factory,
        user_id,
        telegram_chat_id,
    )
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

        task_key = f"parse:{parsing_company_id}"
        progress = await _start_progress(bot, telegram_chat_id, company, locale)

        async def _on_page_scraped(current: int, total: int) -> None:
            if progress:
                await progress.update_bar(task_key, 0, current, total)

        async def _on_vacancy_processed(current: int, total: int) -> None:
            await _report_progress(session_factory, parsing_company_id, current, total)
            if progress:
                await progress.update_bar(task_key, 1, current, total)

        compat_filter = None
        if company.use_compatibility_check and company.compatibility_threshold is not None:
            tech_stack, work_exp_text = await _fetch_user_tech_profile(session_factory, user_id)
            compat_filter = _build_compat_predicate(
                tech_stack, work_exp_text, company.compatibility_threshold
            )

        extractor = ParsingExtractor()
        result = await extractor.run_pipeline(
            search_url=company.search_url,
            keyword_filter=company.keyword_filter,
            target_count=company.target_count,
            blacklisted_ids=blacklisted_ids,
            on_page_scraped=_on_page_scraped,
            on_vacancy_processed=_on_vacancy_processed,
            compat_filter=compat_filter,
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

        if progress:
            await progress.finish_task(task_key)

        try:
            await _notify_user(
                session_factory,
                user_id,
                parsing_company_id,
                bot=bot,
            )
        except Exception as exc:
            logger.error("Failed to notify user", error=str(exc))

        return {
            "status": "completed",
            "vacancies_count": result.vacancy_count,
            "keywords_count": result.keyword_count,
            "skills_count": result.skill_count,
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
    finally:
        if bot:
            await bot.session.close()


async def _init_bot_and_locale(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: int,
    telegram_chat_id: int,
) -> "tuple[Bot | None, str]":  # noqa: F821
    from src.repositories.user import UserRepository

    locale = "ru"
    if not telegram_chat_id:
        return None, locale
    async with session_factory() as session:
        user = await UserRepository(session).get_by_id(user_id)
        if user:
            locale = user.language_code or "ru"
    return _create_bot(), locale


async def _start_progress(
    bot: "Bot | None",  # noqa: F821
    chat_id: int,
    company: "ParsingCompany",  # noqa: F821
    locale: str,
) -> "ProgressService | None":  # noqa: F821
    """Create a ProgressService and register the parsing task bars."""
    if not bot or not chat_id:
        return None
    from src.core.i18n import get_text
    from src.services.progress_service import ProgressService, create_progress_redis

    svc = ProgressService(bot, chat_id, create_progress_redis(), locale)
    await svc.start_task(
        task_key=f"parse:{company.id}",
        title=company.vacancy_title,
        bar_labels=[
            get_text("progress-bar-scraping", locale),
            get_text("progress-bar-keywords", locale),
        ],
    )
    return svc


def _create_bot() -> "Bot":  # noqa: F821
    from src.services.telegram.bot_factory import create_task_bot

    return create_task_bot()


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
    result: "PipelineResult",  # noqa: F821
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

        for vac_data in result.vacancies:
            session.add(
                ParsedVacancy(
                    parsing_company_id=parsing_company_id,
                    hh_vacancy_id=vac_data.hh_vacancy_id,
                    url=vac_data.url,
                    title=vac_data.title,
                    description=vac_data.description,
                    raw_skills=vac_data.raw_skills,
                    ai_keywords=vac_data.ai_keywords,
                )
            )

        session.add(
            AggregatedResult(
                parsing_company_id=parsing_company_id,
                top_keywords=dict(result.keywords),
                top_skills=dict(result.skills),
            )
        )

        if company:
            company.status = "completed"
            company.vacancies_processed = result.vacancy_count
            company.completed_at = datetime.now(UTC).replace(tzinfo=None)

        settings_repo = AppSettingRepository(session)
        bl_days = await settings_repo.get_value("blacklist_days", default=30)
        bl_until = (datetime.now(UTC) + timedelta(days=int(bl_days))).replace(tzinfo=None)
        vacancy_title = company.vacancy_title if company else ""

        for vac_data in result.vacancies:
            stmt = (
                pg_insert(VacancyBlacklist)
                .values(
                    user_id=user_id,
                    vacancy_title_context=vacancy_title,
                    hh_vacancy_id=vac_data.hh_vacancy_id,
                    vacancy_url=vac_data.url,
                    vacancy_name=vac_data.title,
                    blacklisted_until=bl_until,
                )
                .on_conflict_do_update(
                    constraint="uq_user_vacancy_context",
                    set_={
                        "vacancy_url": vac_data.url,
                        "vacancy_name": vac_data.title,
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
                result_data={"vacancies_count": result.vacancy_count},
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


async def _fetch_user_tech_profile(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: int,
) -> tuple[list[str], str]:
    """Return (tech_stack_list, work_experience_text) for the given user.

    Prefers explicit tech_stack from autoparse_settings; falls back to active
    work experience records.
    """
    from src.repositories.user import UserRepository
    from src.repositories.work_experience import WorkExperienceRepository

    async with session_factory() as session:
        user = await UserRepository(session).get_by_id(user_id)
        experiences = await WorkExperienceRepository(session).get_active_by_user(user_id)

    autoparse_settings: dict = (user.autoparse_settings or {}) if user else {}
    explicit_stack: list[str] = autoparse_settings.get("tech_stack") or []

    if explicit_stack:
        tech_stack = explicit_stack
    else:
        tech_stack = [
            kw.strip() for exp in experiences for kw in exp.stack.split(",") if kw.strip()
        ]

    from src.services.formatters import format_work_experience_block

    work_exp_text = format_work_experience_block(experiences)
    return tech_stack, work_exp_text


def _build_compat_predicate(
    tech_stack: list[str],
    work_exp_text: str,
    threshold: int,
) -> Callable[["VacancyData"], Awaitable[bool]]:  # noqa: F821
    """Return an async predicate that scores a vacancy and checks the threshold.

    The predicate is intentionally free of its own semaphore — the extractor's
    ai_sem controls concurrency so compat checks and keyword extractions share
    the same limit.
    """
    from src.services.ai.client import AIClient

    ai_client = AIClient()

    async def predicate(vac) -> bool:
        score = await ai_client.calculate_compatibility(
            vacancy_title=vac.title,
            vacancy_skills=vac.raw_skills or [],
            vacancy_description=vac.description,
            user_tech_stack=tech_stack,
            user_work_experience=work_exp_text,
        )
        return score >= threshold

    return predicate


async def _notify_user(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: int,
    parsing_company_id: int,
    *,
    bot: "Bot | None" = None,  # noqa: F821
) -> None:
    from src.core.i18n import get_text
    from src.repositories.user import UserRepository

    async with session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get_by_id(user_id)
        if not user:
            return

    locale = user.language_code or "ru"

    from src.bot.modules.parsing.keyboards import format_choice_keyboard
    from src.services.ai.streaming import _send_with_retry

    owns_bot = bot is None
    if owns_bot:
        bot = _create_bot()
    try:
        text = get_text("parsing-completed", locale, id=str(parsing_company_id))
        kb = format_choice_keyboard(parsing_company_id, locale=locale)
        await _send_with_retry(
            bot,
            user.telegram_id,
            text=text,
            parse_mode="HTML",
            reply_markup=kb,
        )
    finally:
        if owns_bot:
            await bot.session.close()
