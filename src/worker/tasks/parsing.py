"""Celery task for the full parsing pipeline."""

import asyncio
import random
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.logging import get_logger
from src.worker.app import celery_app
from src.worker.utils import run_async

logger = get_logger(__name__)

_PROGRESS_BAR_WIDTH = 20
_PROGRESS_THROTTLE_MS = 500

_PROGRESS_LABELS: dict[str, dict[str, str]] = {
    "ru": {"title": "Обработка вакансий", "vacancies": "вакансий", "of": "из"},
    "en": {"title": "Processing vacancies", "vacancies": "vacancies", "of": "of"},
}


class _ProgressTracker:
    """Sends live progress bar updates to Telegram via ``send_message_draft``."""

    def __init__(
        self,
        bot: "Bot",  # noqa: F821
        chat_id: int,
        *,
        vacancy_title: str,
        target_count: int,
        keyword_filter: str,
        locale: str = "ru",
    ) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._draft_id = random.randint(1, 2**31 - 1)
        self._vacancy_title = vacancy_title
        self._target_count = target_count
        self._keyword_filter = keyword_filter
        self._labels = _PROGRESS_LABELS.get(locale, _PROGRESS_LABELS["ru"])
        self._last_send: float = 0.0
        self._lock = asyncio.Lock()

    async def update(self, current: int, total: int) -> None:
        from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

        now = time.monotonic()
        is_last = current >= total

        async with self._lock:
            elapsed_ms = (now - self._last_send) * 1000
            if elapsed_ms < _PROGRESS_THROTTLE_MS and not is_last:
                return
            self._last_send = time.monotonic()

        text = self._build_text(current, total)
        try:
            await self._bot.send_message_draft(
                chat_id=self._chat_id,
                draft_id=self._draft_id,
                text=text,
                parse_mode="HTML",
            )
        except TelegramRetryAfter as exc:
            logger.warning("Progress draft flood control", retry_after=exc.retry_after)
            await asyncio.sleep(exc.retry_after)
        except TelegramBadRequest as exc:
            logger.warning("Progress draft failed", error=str(exc))

    def _build_text(self, current: int, total: int) -> str:
        pct = round(current / total * 100) if total else 0
        filled = round(_PROGRESS_BAR_WIDTH * current / total) if total else 0
        bar = "\u2588" * filled + "\u2591" * (_PROGRESS_BAR_WIDTH - filled)

        lb = self._labels
        lines = [
            f"<b>\u23f3 {lb['title']}</b>",
            "",
            f"<b>\U0001f4cb</b> {self._vacancy_title}",
            f"<b>\U0001f3af</b> {self._target_count} {lb['vacancies']}",
        ]
        if self._keyword_filter:
            lines.append(f"<b>\U0001f50e</b> {self._keyword_filter}")
        lines += [
            "",
            f"<code>{bar}</code>  <b>{pct}%</b>",
            f"<i>{current} {lb['of']} {total}</i>",
        ]
        return "\n".join(lines)


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

        tracker = _make_tracker(bot, telegram_chat_id, company, locale)

        async def _on_vacancy_processed(current: int, total: int) -> None:
            await _report_progress(session_factory, parsing_company_id, current, total)
            if tracker:
                await tracker.update(current, total)

        extractor = ParsingExtractor()
        result = await extractor.run_pipeline(
            search_url=company.search_url,
            keyword_filter=company.keyword_filter,
            target_count=company.target_count,
            blacklisted_ids=blacklisted_ids,
            on_vacancy_processed=_on_vacancy_processed,
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


def _make_tracker(
    bot: "Bot | None",  # noqa: F821
    chat_id: int,
    company: "ParsingCompany",  # noqa: F821
    locale: str,
) -> _ProgressTracker | None:
    if not bot or not chat_id:
        return None
    return _ProgressTracker(
        bot,
        chat_id,
        vacancy_title=company.vacancy_title,
        target_count=company.target_count,
        keyword_filter=company.keyword_filter or "",
        locale=locale,
    )


def _create_bot() -> "Bot":  # noqa: F821
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    from src.config import settings as app_settings

    return Bot(
        token=app_settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


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
