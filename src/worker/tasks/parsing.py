"""Celery task for the full parsing pipeline."""

import asyncio
import contextlib
import json
import time
from collections import Counter
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
    "ru": {
        "title": "Обработка вакансий",
        "vacancies": "вакансий",
        "scraping": "Парсинг",
        "keywords": "Ключевые слова",
    },
    "en": {
        "title": "Processing vacancies",
        "vacancies": "vacancies",
        "scraping": "Scraping",
        "keywords": "Keywords",
    },
}


def _bar(current: int, total: int) -> str:
    """Render a single progress bar segment: ``<code>██░░</code> 50%``."""
    pct = round(current / total * 100) if total else 0
    filled = round(_PROGRESS_BAR_WIDTH * current / total) if total else 0
    blocks = "\u2588" * filled + "\u2591" * (_PROGRESS_BAR_WIDTH - filled)
    return f"<code>{blocks}</code>  <b>{pct}%</b>  <i>{current}/{total}</i>"


_PROGRESS_SLOT_TTL = 600  # seconds — safety TTL for Redis slots


class _ProgressTracker:
    """Sends live dual-progress-bar updates to Telegram via ``send_message_draft``.

    Multiple concurrent trackers for the same ``chat_id`` share a single
    deterministic ``draft_id`` and a Redis-backed slot so they compose into
    one combined draft message instead of overwriting each other.
    """

    def __init__(
        self,
        bot: "Bot",  # noqa: F821
        chat_id: int,
        *,
        slot_key: str,
        vacancy_title: str,
        target_count: int,
        keyword_filter: str,
        locale: str = "ru",
    ) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._slot_key = slot_key
        # All trackers for the same chat share the same draft slot in Telegram.
        self._draft_id = abs(chat_id) % (2**31 - 1) + 1
        self._vacancy_title = vacancy_title
        self._target_count = target_count
        self._keyword_filter = keyword_filter
        self._labels = _PROGRESS_LABELS.get(locale, _PROGRESS_LABELS["ru"])
        self._scraped = 0
        self._keywords = 0
        self._total = 0
        self._last_send: float = 0.0
        self._lock = asyncio.Lock()
        self._redis = None

    # ------------------------------------------------------------------
    # Public callbacks
    # ------------------------------------------------------------------

    async def update_scraped(self, current: int, total: int) -> None:
        async with self._lock:
            if current > self._scraped:
                self._scraped = current
            self._total = total
        await self._send_draft(is_last=False)

    async def update_keywords(self, current: int, total: int) -> None:
        is_last = current >= total
        async with self._lock:
            if current > self._keywords:
                self._keywords = current
            self._total = total
        await self._send_draft(is_last=is_last)

    # ------------------------------------------------------------------
    # Redis slot helpers
    # ------------------------------------------------------------------

    def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as aioredis

            from src.config import settings as app_settings

            self._redis = aioredis.Redis.from_url(app_settings.redis_url, decode_responses=True)
        return self._redis

    def _redis_slot_key(self) -> str:
        return f"progress:{self._chat_id}:{self._slot_key}"

    async def _write_slot(self, scraped: int, keywords: int, total: int) -> None:
        data = {
            "scraped": scraped,
            "keywords": keywords,
            "total": total,
            "title": self._vacancy_title,
            "target_count": self._target_count,
            "keyword_filter": self._keyword_filter,
        }
        await self._get_redis().set(self._redis_slot_key(), json.dumps(data), ex=_PROGRESS_SLOT_TTL)

    async def _delete_slot(self) -> None:
        await self._get_redis().delete(self._redis_slot_key())

    async def _read_all_slots(self) -> list[dict]:
        r = self._get_redis()
        keys = await r.keys(f"progress:{self._chat_id}:*")
        if not keys:
            return []
        values = await r.mget(*keys)
        slots = []
        for raw in values:
            if raw:
                with contextlib.suppress(Exception):
                    slots.append(json.loads(raw))
        return slots

    # ------------------------------------------------------------------
    # Draft sending
    # ------------------------------------------------------------------

    async def _send_draft(self, *, is_last: bool) -> None:
        from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

        now = time.monotonic()
        async with self._lock:
            elapsed_ms = (now - self._last_send) * 1000
            if elapsed_ms < _PROGRESS_THROTTLE_MS and not is_last:
                return
            self._last_send = time.monotonic()
            scraped, keywords, total = self._scraped, self._keywords, self._total

        await self._write_slot(scraped, keywords, total)
        slots = await self._read_all_slots()
        text = (
            self._build_combined_text(slots)
            if slots
            else self._build_slot_text(scraped, keywords, total)
        )

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

        if is_last:
            await self._delete_slot()

    # ------------------------------------------------------------------
    # Text builders
    # ------------------------------------------------------------------

    def _build_slot_text(self, scraped: int, keywords: int, total: int) -> str:
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
            f"\U0001f310 {lb['scraping']}",
            _bar(scraped, total),
            "",
            f"\U0001f9e0 {lb['keywords']}",
            _bar(keywords, total),
        ]
        return "\n".join(lines)

    def _build_combined_text(self, slots: list[dict]) -> str:
        lb = self._labels
        parts = []
        for slot in slots:
            scraped = slot.get("scraped", 0)
            keywords = slot.get("keywords", 0)
            total = slot.get("total", 0)
            title = slot.get("title", "")
            target_count = slot.get("target_count", 0)
            keyword_filter = slot.get("keyword_filter", "")
            lines = [
                f"<b>\u23f3 {lb['title']}</b>",
                "",
                f"<b>\U0001f4cb</b> {title}",
                f"<b>\U0001f3af</b> {target_count} {lb['vacancies']}",
            ]
            if keyword_filter:
                lines.append(f"<b>\U0001f50e</b> {keyword_filter}")
            lines += [
                "",
                f"\U0001f310 {lb['scraping']}",
                _bar(scraped, total),
                "",
                f"\U0001f9e0 {lb['keywords']}",
                _bar(keywords, total),
            ]
            parts.append("\n".join(lines))
        return "\n\n\u2500\u2500\u2500\n\n".join(parts)


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

        async def _on_page_scraped(current: int, total: int) -> None:
            if tracker:
                await tracker.update_scraped(current, total)

        async def _on_vacancy_processed(current: int, total: int) -> None:
            await _report_progress(session_factory, parsing_company_id, current, total)
            if tracker:
                await tracker.update_keywords(current, total)

        extractor = ParsingExtractor()
        result = await extractor.run_pipeline(
            search_url=company.search_url,
            keyword_filter=company.keyword_filter,
            target_count=company.target_count,
            blacklisted_ids=blacklisted_ids,
            on_page_scraped=_on_page_scraped,
            on_vacancy_processed=_on_vacancy_processed,
        )

        if company.use_compatibility_check and company.compatibility_threshold is not None:
            tech_stack, work_exp_text = await _fetch_user_tech_profile(session_factory, user_id)
            filtered = await _apply_compatibility_filter(
                result["vacancies"],
                company.compatibility_threshold,
                tech_stack,
                work_exp_text,
            )
            if len(filtered) != len(result["vacancies"]):
                keywords, skills = _recompute_aggregates(filtered)
                result = {"vacancies": filtered, "keywords": keywords, "skills": skills}

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
        slot_key=str(company.id),
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


def _recompute_aggregates(vacancies: list[dict]) -> tuple[dict, dict]:
    """Recount keyword and skill frequencies from a filtered vacancy list."""
    keywords_counter: Counter = Counter()
    skills_counter: Counter = Counter()
    for vac in vacancies:
        for kw in vac.get("ai_keywords") or []:
            keywords_counter[kw.strip()] += 1
        for skill in vac.get("raw_skills") or []:
            skills_counter[str(skill).strip()] += 1
    return dict(keywords_counter.most_common()), dict(skills_counter.most_common())


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

    work_exp_text = "; ".join(f"{exp.company_name}: {exp.stack}" for exp in experiences)
    return tech_stack, work_exp_text


_COMPAT_FILTER_CONCURRENCY = 3


async def _apply_compatibility_filter(
    vacancies: list[dict],
    threshold: int,
    tech_stack: list[str],
    work_exp_text: str,
) -> list[dict]:
    """Keep only vacancies whose compatibility score meets the threshold.

    Uses a semaphore to limit concurrent AI calls.
    """
    from src.services.ai.client import AIClient

    ai_client = AIClient()
    sem = asyncio.Semaphore(_COMPAT_FILTER_CONCURRENCY)

    async def _score_vacancy(vac: dict) -> tuple[dict, float]:
        async with sem:
            score = await ai_client.calculate_compatibility(
                vacancy_title=vac["title"],
                vacancy_skills=vac.get("raw_skills") or [],
                vacancy_description=vac.get("description", ""),
                user_tech_stack=tech_stack,
                user_work_experience=work_exp_text,
            )
        return vac, score

    scored = await asyncio.gather(*[_score_vacancy(v) for v in vacancies])
    kept = [vac for vac, score in scored if score >= threshold]
    logger.info(
        "Compatibility filter applied",
        total=len(vacancies),
        kept=len(kept),
        threshold=threshold,
    )
    return kept


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
