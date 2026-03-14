"""Celery task for the full parsing pipeline."""

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.logging import get_logger
from src.worker.app import celery_app
from src.worker.base_task import HHBotTask
from src.worker.utils import run_async

logger = get_logger(__name__)

_STALENESS_CHECK_INTERVAL = 30


class ParsingStalenessError(Exception):
    """Raised when no parsing progress has occurred within the staleness window."""



def _is_transient_failure(exc: Exception) -> bool:
    """Return True if the failure is transient and should not open the circuit breaker."""
    if getattr(exc, "status_code", None) == 429:
        return True
    from openai import APIStatusError, RateLimitError

    if isinstance(exc, RateLimitError):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code == 429
    return False


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="parsing.run_company",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=7200,
    time_limit=7260,
)
def run_parsing_company(
    self,
    parsing_company_id: int,
    user_id: int,
    include_blacklisted: bool = False,
    telegram_chat_id: int = 0,
) -> dict:
    try:
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
    except ParsingStalenessError as err:
        logger.warning(
            "Parsing task stalled: no progress in staleness window",
            company_id=parsing_company_id,
            user_id=user_id,
        )
        run_async(
            lambda sf, _err=err: _handle_parsing_staleness(
                sf, parsing_company_id, user_id, telegram_chat_id, _err
            )
        )
        raise


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
    from src.services.parser.scraper import HHScraper
    from src.services.staleness_progress import (
        create_staleness_redis,
        is_stale,
    )
    from src.services.staleness_progress import (
        record_progress as record_staleness_progress,
    )
    from src.services.task_checkpoint import TaskCheckpointService, create_checkpoint_redis
    from src.worker.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker("parsing")
    checkpoint = TaskCheckpointService(create_checkpoint_redis())
    checkpoint_key = f"parse:{parsing_company_id}"
    task_id = task.request.id or ""

    async with session_factory() as session:
        settings_repo = AppSettingRepository(session)

        enabled = await settings_repo.get_value("task_parsing_enabled", default=True)
        if not enabled:
            logger.warning("Parsing task disabled via settings")
            return {"status": "disabled"}

        cb_threshold = await settings_repo.get_value("cb_parsing_failure_threshold", default=5)
        cb_timeout = await settings_repo.get_value("cb_parsing_recovery_timeout", default=60)
        staleness_window = int(
            await settings_repo.get_value("parsing_staleness_window_seconds", default=180)
        )
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
            if company.is_deleted:
                logger.info("Parsing company soft-deleted, skipping", company_id=parsing_company_id)
                return {"status": "deleted"}

            await company_repo.update(company, status="processing")
            await session.commit()

            blacklisted_ids: set[str] = set()
            if not include_blacklisted:
                bl_repo = BlacklistRepository(session)
                blacklisted_ids = await bl_repo.get_active_ids(
                    user_id,
                    company.vacancy_title,
                )

            settings_repo = AppSettingRepository(session)
            bl_days = await settings_repo.get_value("blacklist_days", default=30)
            bl_until = (datetime.now(UTC) + timedelta(days=int(bl_days))).replace(tzinfo=None)

        task_key = f"parse:{parsing_company_id}"
        staleness_redis = create_staleness_redis()
        await record_staleness_progress(staleness_redis, task_key)

        progress = await _start_progress(
            bot, telegram_chat_id, company, locale, celery_task_id=task.request.id
        )

        compat_params = None
        if company.use_compatibility_check and company.compatibility_threshold is not None:
            tech_stack, work_exp_text = await _fetch_user_tech_profile(session_factory, user_id)
            compat_params = (
                tech_stack,
                work_exp_text,
                company.compatibility_threshold,
            )

        use_compat = compat_params is not None
        vacancies: list[dict] = []
        resume_from: tuple[list[dict], int] | None = None

        restored = await checkpoint.load_parsing(checkpoint_key, task_id)
        if not restored:
            restored = await checkpoint.load_parsing_for_resume(checkpoint_key)
        if restored:
            skip_count, _, urls = restored[0], restored[1], restored[2]
            vacancies = list(urls)
            resume_from = (vacancies, skip_count)
            logger.info(
                "Resuming parsing from checkpoint",
                company_id=parsing_company_id,
                skip_count=skip_count,
                total=len(vacancies),
            )
        elif not use_compat:
            scraper = HHScraper()
            vacancies = await scraper.collect_vacancy_urls(
                company.search_url,
                company.keyword_filter,
                company.target_count,
                blacklisted_ids=blacklisted_ids,
            )
            resume_from = (vacancies, 0) if vacancies else None

        async def _on_page_scraped(current: int, total: int) -> None:
            await record_staleness_progress(staleness_redis, task_key)
            if progress:
                display_total = company.target_count if use_compat else total
                await progress.update_bar(task_key, 0, current, display_total)

        async def _on_urls_fetched(new_urls: list[dict]) -> None:
            # Do NOT extend vacancies here: extractor already did vacancies.extend(batch)
            # before calling this callback. Extending again would duplicate URLs.
            if new_urls:
                await checkpoint.save_parsing(
                    checkpoint_key,
                    task_id,
                    processed=len(vacancies) - len(new_urls),
                    total=len(vacancies),
                    urls=vacancies,
                )

        async def _on_vacancy_processed(
            current: int, total: int, vacancy_data: "VacancyData | None" = None  # noqa: F821
        ) -> None:
            await record_staleness_progress(staleness_redis, task_key)
            await _report_progress(session_factory, parsing_company_id, current, total)
            if progress:
                display_total = company.target_count if use_compat else total
                await progress.update_bar(task_key, 1, current, display_total)
            if vacancies and current > 0:
                await checkpoint.save_parsing(
                    checkpoint_key,
                    task_id,
                    processed=current,
                    total=total,
                    urls=vacancies,
                )
            if vacancy_data is not None:
                await _save_single_vacancy(
                    session_factory,
                    parsing_company_id,
                    user_id,
                    vacancy_data,
                    company.vacancy_title,
                    bl_until,
                )

        async def _staleness_checker() -> None:
            while True:
                await asyncio.sleep(_STALENESS_CHECK_INTERVAL)
                if await is_stale(staleness_redis, task_key, float(staleness_window)):
                    return

        extractor = ParsingExtractor()
        pipeline_coro = extractor.run_pipeline(
            search_url=company.search_url,
            keyword_filter=company.keyword_filter,
            target_count=company.target_count,
            blacklisted_ids=blacklisted_ids,
            on_page_scraped=_on_page_scraped,
            on_vacancy_processed=_on_vacancy_processed,
            on_urls_fetched=_on_urls_fetched if use_compat else None,
            compat_params=compat_params,
            resume_from=resume_from,
        )
        pipeline_task = asyncio.create_task(pipeline_coro)
        checker_task = asyncio.create_task(_staleness_checker())

        done, pending = await asyncio.wait(
            [pipeline_task, checker_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        if checker_task in done:
            pipeline_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pipeline_task
            raise ParsingStalenessError(
                f"No progress in the last {staleness_window} seconds"
            )
        checker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await checker_task
        result = pipeline_task.result()

        vacancies_count, keywords_count, skills_count = await _save_parsing_results(
            session_factory,
            parsing_company_id,
            user_id,
            task,
            result,
            idempotency_key,
        )
        cb.record_success()
        await checkpoint.clear(checkpoint_key)

        if progress:
            shortage_note = None
            if use_compat and vacancies_count < company.target_count:
                from src.core.i18n import get_text

                shortage_note = get_text(
                    "progress-parsing-shortage",
                    locale,
                    count=vacancies_count,
                    target=company.target_count,
                    entity=get_text("progress-entity-vacancies", locale),
                )
            await progress.finish_task(task_key, shortage_note=shortage_note)

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
            "vacancies_count": vacancies_count,
            "keywords_count": keywords_count,
            "skills_count": skills_count,
        }

    except Exception as exc:
        if not _is_transient_failure(exc):
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
    celery_task_id: str | None = None,
) -> "ProgressService | None":  # noqa: F821
    """Create a ProgressService and register the parsing task bars."""
    if not bot or not chat_id:
        return None
    from src.core.i18n import get_text
    from src.services.progress_service import ProgressService, create_progress_redis

    use_compat_display = (
        company.use_compatibility_check and company.compatibility_threshold is not None
    )
    initial_totals = (
        [company.target_count, company.target_count] if use_compat_display else None
    )
    svc = ProgressService(bot, chat_id, create_progress_redis(), locale)
    await svc.start_task(
        task_key=f"parse:{company.id}",
        title=company.vacancy_title,
        bar_labels=[
            get_text("progress-bar-scraping", locale),
            get_text("progress-bar-keywords", locale),
        ],
        celery_task_id=celery_task_id,
        initial_totals=initial_totals,
    )
    return svc


def _create_bot() -> "Bot":  # noqa: F821
    from src.services.telegram.bot_factory import create_task_bot

    return create_task_bot()


async def _save_single_vacancy(
    session_factory: async_sessionmaker[AsyncSession],
    parsing_company_id: int,
    user_id: int,
    vac_data: "VacancyData",  # noqa: F821
    vacancy_title: str,
    bl_until: datetime,
) -> None:
    """Persist a single processed vacancy and its blacklist entry. Used for incremental save."""
    from src.models.blacklist import VacancyBlacklist
    from src.models.parsing import ParsedVacancy

    async with session_factory() as session:
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
        await session.commit()


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
) -> tuple[int, int, int]:
    """Save final parsing results.

    ParsedVacancy and VacancyBlacklist are already saved incrementally.
    Returns (vacancies_count, keywords_count, skills_count) for the task response.
    """
    from collections import Counter

    from sqlalchemy import select

    from src.models.parsing import AggregatedResult, ParsedVacancy
    from src.models.task import BaseCeleryTask
    from src.repositories.parsing import ParsingCompanyRepository

    async with session_factory() as session:
        company_repo = ParsingCompanyRepository(session)
        company = await company_repo.get_by_id(parsing_company_id)

        # Recompute AggregatedResult from all ParsedVacancy for this company
        stmt = select(ParsedVacancy).where(ParsedVacancy.parsing_company_id == parsing_company_id)
        rows = (await session.execute(stmt)).scalars().all()
        keywords_counter: Counter[str] = Counter()
        skills_counter: Counter[str] = Counter()
        for vac in rows:
            if vac.ai_keywords:
                for kw in vac.ai_keywords:
                    if isinstance(kw, str) and kw.strip():
                        keywords_counter[kw.strip()] += 1
            if vac.raw_skills:
                for skill in vac.raw_skills:
                    if isinstance(skill, str) and skill.strip():
                        skills_counter[skill.strip()] += 1

        top_keywords = dict(keywords_counter.most_common())
        top_skills = dict(skills_counter.most_common())
        vacancies_count = len(rows)

        # Upsert AggregatedResult
        existing = (
            await session.execute(
                select(AggregatedResult).where(
                    AggregatedResult.parsing_company_id == parsing_company_id
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.top_keywords = top_keywords
            existing.top_skills = top_skills
        else:
            session.add(
                AggregatedResult(
                    parsing_company_id=parsing_company_id,
                    top_keywords=top_keywords,
                    top_skills=top_skills,
                )
            )

        if company:
            company.status = "completed"
            # vacancies_processed is already updated by _report_progress via on_vacancy_processed
            company.completed_at = datetime.now(UTC).replace(tzinfo=None)

        session.add(
            BaseCeleryTask(
                celery_task_id=task.request.id if task.request else None,
                task_type="parse_company",
                user_id=user_id,
                status="completed",
                idempotency_key=idempotency_key,
                result_data={"vacancies_count": vacancies_count},
            )
        )

        await session.commit()
        return vacancies_count, len(top_keywords), len(top_skills)


async def _handle_parsing_staleness(
    session_factory: async_sessionmaker[AsyncSession],
    parsing_company_id: int,
    user_id: int,
    telegram_chat_id: int,
    err: ParsingStalenessError,
) -> None:
    """Notify user when parsing stalled (no progress in staleness window)."""
    if not telegram_chat_id:
        return
    import re

    from src.core.i18n import get_text
    from src.repositories.user import UserRepository
    from src.services.telegram.bot_factory import create_task_bot

    async with session_factory() as session:
        user = await UserRepository(session).get_by_id(user_id)
        locale = (user.language_code or "ru") if user else "ru"

    minutes = 3
    match = re.search(r"last (\d+) seconds", str(err))
    if match:
        minutes = max(1, int(match.group(1)) // 60)

    bot = create_task_bot()
    try:
        text = get_text("parsing-staleness-error", locale, minutes=minutes)
        await bot.send_message(
            chat_id=telegram_chat_id,
            text=text,
            parse_mode="HTML",
        )
    finally:
        await bot.session.close()


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


async def _notify_user(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: int,
    parsing_company_id: int,
    *,
    bot: "Bot | None" = None,  # noqa: F821
) -> None:
    from src.core.i18n import get_text
    from src.repositories.parsing import ParsingCompanyRepository
    from src.repositories.user import UserRepository

    async with session_factory() as session:
        company_repo = ParsingCompanyRepository(session)
        company = await company_repo.get_by_id(parsing_company_id)
        if company and company.is_deleted:
            logger.info(
                "Skipping notification for soft-deleted parsing",
                company_id=parsing_company_id,
            )
            return

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
