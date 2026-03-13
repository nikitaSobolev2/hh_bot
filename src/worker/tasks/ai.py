"""Celery task for AI key phrases generation with streaming to Telegram."""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.logging import get_logger
from src.worker.app import celery_app
from src.worker.base_task import HHBotTask
from src.worker.utils import run_async

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="ai.generate_key_phrases",
    max_retries=1,
    default_retry_delay=15,
    soft_time_limit=300,
    time_limit=360,
)
def generate_key_phrases_task(
    self,
    parsing_company_id: int,
    user_id: int,
    style: str,
    keyword_count: int,
    telegram_chat_id: int,
    lang: str,
    mode: str = "",
) -> dict:
    return run_async(
        lambda sf: _generate_key_phrases_async(
            sf,
            self,
            parsing_company_id,
            user_id,
            style,
            keyword_count,
            telegram_chat_id,
            lang,
            mode,
        )
    )


def _build_idempotency_key(
    parsing_company_id: int,
    style: str,
    keyword_count: int,
    lang: str,
    mode: str = "",
) -> str:
    time_bucket = int(datetime.now(UTC).timestamp()) // 300
    return f"keyphrase:{parsing_company_id}:{style}:{keyword_count}:{lang}:{mode}:{time_bucket}"


async def _save_task_record(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    celery_task,
    user_id: int,
    idempotency_key: str,
    parsing_company_id: int,
    style: str,
    keyword_count: int,
    status: str,
    phrases: str | None = None,
    error_message: str | None = None,
) -> None:
    from sqlalchemy.exc import IntegrityError

    from src.models.task import CompanyCreateKeyPhrasesTask

    celery_task_id = celery_task.request.id if celery_task.request else None

    async with session_factory() as session:
        record = CompanyCreateKeyPhrasesTask(
            celery_task_id=celery_task_id,
            task_type="create_key_phrases",
            user_id=user_id,
            status=status,
            idempotency_key=idempotency_key,
            parsing_company_id=parsing_company_id,
            style=style,
            keyword_count=keyword_count,
            generated_phrases=phrases,
            error_message=error_message,
        )
        session.add(record)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            logger.warning(
                "Task record already exists, skipping",
                idempotency_key=idempotency_key,
                status=status,
            )


async def _stream_with_fallback(
    ai,
    bot,
    chat_id: int,
    header: str,
    prompt: str,
) -> str:
    from src.services.ai.streaming import _send_with_retry, stream_to_telegram

    try:
        return await stream_to_telegram(
            bot=bot,
            chat_id=chat_id,
            token_stream=ai.stream_key_phrases(prompt),
            initial_text=header,
            parse_mode="HTML",
        )
    except Exception:
        logger.warning(
            "Streaming failed, falling back to non-streaming API",
        )
        phrases = await ai.generate_key_phrases(prompt)
        if not phrases:
            raise
        final_header = header.replace("\u23f3", "\u2705").replace("...", "")
        final_text = final_header + phrases
        if len(final_text) > 4096:
            final_text = final_text[-4000:]
        await _send_with_retry(bot, chat_id, text=final_text, parse_mode="HTML")
        return phrases


def _build_prompt(
    vacancy_title: str,
    main_keywords: list[str],
    secondary_keywords: list[str],
    style_label: str,
    keyword_count: int,
    lang: str,
    mode: str,
    work_experiences: list | None,
) -> str:
    from src.services.ai.prompts import (
        WorkExperienceEntry,
        build_key_phrases_prompt,
        build_per_company_key_phrases_prompt,
    )

    if mode == "w" and work_experiences:
        entries = [
            WorkExperienceEntry(
                company_name=we["company_name"],
                stack=we["stack"],
                title=we.get("title"),
                period=we.get("period"),
                achievements=we.get("achievements"),
                duties=we.get("duties"),
            )
            for we in work_experiences
        ]
        return build_per_company_key_phrases_prompt(
            resume_title=vacancy_title,
            main_keywords=main_keywords,
            secondary_keywords=secondary_keywords,
            style=style_label,
            per_company_count=keyword_count,
            language=lang,
            work_experiences=entries,
        )

    return build_key_phrases_prompt(
        resume_title=vacancy_title,
        main_keywords=main_keywords,
        secondary_keywords=secondary_keywords,
        style=style_label,
        count=keyword_count,
        language=lang,
    )


async def _load_work_experiences(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: int,
) -> list[dict]:
    from src.repositories.work_experience import WorkExperienceRepository

    async with session_factory() as session:
        repo = WorkExperienceRepository(session)
        entries = await repo.get_active_by_user(user_id)
        return [
            {
                "company_name": e.company_name,
                "stack": e.stack,
                "title": e.title,
                "period": e.period,
                "achievements": e.achievements,
                "duties": e.duties,
            }
            for e in entries
        ]


async def _generate_key_phrases_async(
    session_factory: async_sessionmaker[AsyncSession],
    task,
    parsing_company_id: int,
    user_id: int,
    style: str,
    keyword_count: int,
    telegram_chat_id: int,
    lang: str,
    mode: str = "",
) -> dict:
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    from src.bot.modules.parsing.keyboards import KEY_PHRASES_LANGUAGES
    from src.config import settings as app_settings
    from src.core.i18n import get_text
    from src.repositories.app_settings import AppSettingRepository
    from src.repositories.parsing import (
        AggregatedResultRepository,
        ParsingCompanyRepository,
    )
    from src.repositories.task import CeleryTaskRepository
    from src.repositories.user import UserRepository
    from src.services.ai.client import AIClient
    from src.worker.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker("keyphrase")

    async with session_factory() as session:
        settings_repo = AppSettingRepository(session)
        enabled = await settings_repo.get_value("task_keyphrase_enabled", default=True)
        if not enabled:
            return {"status": "disabled"}

        cb_threshold = await settings_repo.get_value("cb_keyphrase_failure_threshold", default=5)
        cb_timeout = await settings_repo.get_value("cb_keyphrase_recovery_timeout", default=60)
        cb.update_config(
            failure_threshold=int(cb_threshold),
            recovery_timeout=int(cb_timeout),
        )

    if not cb.is_call_allowed():
        return {"status": "circuit_open"}

    idempotency_key = _build_idempotency_key(parsing_company_id, style, keyword_count, lang, mode)

    async with session_factory() as session:
        task_repo = CeleryTaskRepository(session)
        existing = await task_repo.get_by_idempotency_key(idempotency_key)
        if existing and existing.status == "completed":
            return {"status": "already_completed"}

    locale = "ru"
    async with session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        if user:
            locale = user.language_code or "ru"

    work_experiences: list[dict] | None = None
    if mode == "w":
        work_experiences = await _load_work_experiences(session_factory, user_id)

    try:
        async with session_factory() as session:
            agg_repo = AggregatedResultRepository(session)
            company_repo = ParsingCompanyRepository(session)

            company = await company_repo.get_by_id(parsing_company_id)
            if not company:
                return {"status": "error", "message": "Company not found"}

            agg = await agg_repo.get_by_company(parsing_company_id)
            if not agg or not agg.top_keywords:
                return {"status": "error", "message": "No aggregated keywords"}

            sorted_kw = sorted(agg.top_keywords.items(), key=lambda x: -x[1])
            main_keywords = [kw for kw, _ in sorted_kw[:30]]
            secondary_keywords = [kw for kw, _ in sorted_kw[30:60]]

        style_label = get_text(f"style-{style}", locale)
        lang_label = KEY_PHRASES_LANGUAGES.get(lang, lang)

        prompt = _build_prompt(
            company.vacancy_title,
            main_keywords,
            secondary_keywords,
            style_label,
            keyword_count,
            lang,
            mode,
            work_experiences,
        )

        ai = AIClient()
        bot = Bot(
            token=app_settings.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        try:
            header = (
                get_text(
                    "keyphrase-header",
                    locale,
                    title=company.vacancy_title,
                )
                + "\n"
                + get_text(
                    "keyphrase-style-label",
                    locale,
                    style=style_label,
                    lang=lang_label,
                )
                + "\n\n"
            )
            phrases = await _stream_with_fallback(ai, bot, telegram_chat_id, header, prompt)
        finally:
            await bot.session.close()

        async with session_factory() as session:
            agg_repo = AggregatedResultRepository(session)
            agg = await agg_repo.get_by_company(parsing_company_id)
            if agg:
                agg.key_phrases = phrases
                agg.key_phrases_style = style_label
            await session.commit()

        await _save_task_record(
            session_factory,
            celery_task=task,
            user_id=user_id,
            idempotency_key=idempotency_key,
            parsing_company_id=parsing_company_id,
            style=style,
            keyword_count=keyword_count,
            status="completed",
            phrases=phrases,
        )

        cb.record_success()
        return {"status": "completed", "phrases_length": len(phrases or "")}

    except Exception as exc:
        cb.record_failure()

        await _save_task_record(
            session_factory,
            celery_task=task,
            user_id=user_id,
            idempotency_key=idempotency_key,
            parsing_company_id=parsing_company_id,
            style=style,
            keyword_count=keyword_count,
            status="failed",
            error_message=str(exc),
        )

        logger.error("Key phrases task failed", error=str(exc))
        raise
