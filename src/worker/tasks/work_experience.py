"""Celery task for AI generation of work experience achievements and duties."""

from __future__ import annotations

from src.core.logging import get_logger
from src.worker.app import celery_app
from src.worker.base_task import HHBotTask
from src.worker.utils import run_async

logger = get_logger(__name__)

_MODE_CREATE = "create"
_MODE_EDIT = "edit"


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="work_experience.generate_ai",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=240,
    time_limit=300,
)
def generate_work_experience_ai_task(
    self,
    user_id: int,
    chat_id: int,
    message_id: int,
    field: str,
    mode: str,
    locale: str = "ru",
    company_name: str = "",
    title: str | None = None,
    stack: str = "",
    period: str | None = None,
    return_to: str = "menu",
    work_exp_id: int | None = None,
) -> dict:
    return run_async(
        lambda sf: _generate_async(
            sf,
            user_id=user_id,
            chat_id=chat_id,
            message_id=message_id,
            field=field,
            mode=mode,
            locale=locale,
            company_name=company_name,
            title=title,
            stack=stack,
            period=period,
            return_to=return_to,
            work_exp_id=work_exp_id,
        )
    )


async def _generate_async(
    session_factory,
    *,
    user_id: int,
    chat_id: int,
    message_id: int,
    field: str,
    mode: str,
    locale: str,
    company_name: str,
    title: str | None,
    stack: str,
    period: str | None,
    return_to: str,
    work_exp_id: int | None,
) -> dict:
    from src.services.ai.client import AIClient
    from src.worker.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker("work_experience_ai")
    if not cb.is_call_allowed():
        logger.warning("Circuit breaker open, skipping WE AI generation", user_id=user_id)
        return {"status": "circuit_open"}

    if mode == _MODE_EDIT:
        async with session_factory() as session:
            from src.repositories.work_experience import WorkExperienceRepository

            repo = WorkExperienceRepository(session)
            exp = await repo.get_by_id(work_exp_id)
            if not exp:
                return {"status": "not_found"}
            company_name = exp.company_name
            title = exp.title
            stack = exp.stack
            period = exp.period

    prompt, system_prompt = _build_prompt(field, company_name, stack, title, period)
    ai_client = AIClient()

    try:
        generated = await ai_client.generate_text(
            prompt, system_prompt=system_prompt, max_tokens=800, temperature=0.6
        )
        cb.record_success()
    except Exception as exc:
        cb.record_failure()
        logger.error(
            "WE AI generation failed",
            user_id=user_id,
            field=field,
            mode=mode,
            error=str(exc),
        )
        raise

    if mode == _MODE_CREATE:
        async with session_factory() as session:
            from src.repositories.work_experience_ai_draft import WorkExperienceAiDraftRepository

            draft_repo = WorkExperienceAiDraftRepository(session)
            await draft_repo.upsert(user_id, field, generated or "")
            await session.commit()

        await _notify_user_create(
            chat_id=chat_id,
            message_id=message_id,
            user_id=user_id,
            field=field,
            generated=generated or "",
            return_to=return_to,
            locale=locale,
        )
    else:
        async with session_factory() as session:
            from src.repositories.work_experience import WorkExperienceRepository

            repo = WorkExperienceRepository(session)
            exp = await repo.get_by_id(work_exp_id)
            if exp and exp.user_id == user_id:
                await repo.update(exp, **{field: generated or None})
                await session.commit()

        await _notify_user_edit(
            chat_id=chat_id,
            message_id=message_id,
            work_exp_id=work_exp_id,
            return_to=return_to,
            field=field,
            locale=locale,
        )

    return {"status": "completed", "field": field, "mode": mode}


def _build_prompt(
    field: str,
    company_name: str,
    stack: str,
    title: str | None,
    period: str | None,
) -> tuple[str, str]:
    from src.services.ai.prompts import (
        build_work_experience_achievements_prompt,
        build_work_experience_achievements_system_prompt,
        build_work_experience_duties_prompt,
        build_work_experience_duties_system_prompt,
    )

    if field == "achievements":
        return (
            build_work_experience_achievements_prompt(
                company_name, stack, title=title, period=period
            ),
            build_work_experience_achievements_system_prompt(),
        )
    return (
        build_work_experience_duties_prompt(company_name, stack, title=title, period=period),
        build_work_experience_duties_system_prompt(),
    )


async def _notify_user_create(
    *,
    chat_id: int,
    message_id: int,
    user_id: int,
    field: str,
    generated: str,
    return_to: str,
    locale: str,
) -> None:
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.bot.modules.work_experience.callbacks import WorkExpCallback
    from src.config import settings
    from src.core.i18n import get_text

    text_key = (
        "work-exp-ai-result-achievements"
        if field == "achievements"
        else "work-exp-ai-result-duties"
    )
    message_text = get_text(text_key, locale, text=generated)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_text("we-btn-accept-draft", locale),
                    callback_data=WorkExpCallback(
                        action="accept_draft",
                        field=field,
                        return_to=return_to,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_text("we-btn-regenerate", locale),
                    callback_data=WorkExpCallback(
                        action="generate_ai",
                        field=field,
                        return_to=return_to,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_text("btn-skip", locale),
                    callback_data=WorkExpCallback(
                        action="skip_field",
                        field=field,
                        return_to=return_to,
                    ).pack(),
                )
            ],
        ]
    )

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=message_text,
                reply_markup=keyboard,
            )
        except TelegramBadRequest:
            await bot.send_message(
                chat_id=chat_id,
                text=message_text,
                reply_markup=keyboard,
            )
    finally:
        await bot.session.close()


async def _notify_user_edit(
    *,
    chat_id: int,
    message_id: int,
    work_exp_id: int | None,
    return_to: str,
    field: str,
    locale: str,
) -> None:
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.bot.modules.work_experience.callbacks import WorkExpCallback
    from src.config import settings
    from src.core.i18n import get_text

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_text("we-btn-view-result", locale),
                    callback_data=WorkExpCallback(
                        action="detail",
                        work_exp_id=work_exp_id or 0,
                        return_to=return_to,
                    ).pack(),
                )
            ]
        ]
    )

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=get_text("work-exp-ai-generation-done", locale),
                reply_markup=keyboard,
            )
        except TelegramBadRequest:
            await bot.send_message(
                chat_id=chat_id,
                text=get_text("work-exp-ai-generation-done", locale),
                reply_markup=keyboard,
            )
    finally:
        await bot.session.close()


# ── Resume key phrases ────────────────────────────────────────────────────────

_COMPANY_BLOCK_PATTERN = r"(?:Компания|Company)\s*:\s*(.+?)(?=(?:Компания|Company)\s*:|$)"


def _parse_keyphrases_by_company(raw: str) -> dict[str, str]:
    """Parse the AI keyphrase output into a {company_name: phrases_text} dict."""
    import re

    blocks: dict[str, str] = {}
    parts = re.split(r"(?:Компания|Company)\s*:\s*", raw)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        lines = part.splitlines()
        company_name = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        if company_name and body:
            blocks[company_name] = body
    return blocks


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="work_experience.generate_resume_keyphrases",
    max_retries=1,
    default_retry_delay=30,
    soft_time_limit=300,
    time_limit=360,
)
def generate_resume_key_phrases_task(
    self,
    user_id: int,
    chat_id: int,
    message_id: int,
    locale: str = "ru",
    extra_keywords: list[str] | None = None,
    secondary_keywords: list[str] | None = None,
    resume_id: int | None = None,
    job_title: str | None = None,
    skill_level: str | None = None,
    disabled_exp_ids: list[int] | None = None,
) -> dict:
    return run_async(
        lambda sf: _generate_resume_keyphrases_async(
            sf,
            user_id=user_id,
            chat_id=chat_id,
            message_id=message_id,
            locale=locale,
            extra_keywords=extra_keywords,
            secondary_keywords=secondary_keywords,
            resume_id=resume_id,
            job_title=job_title,
            skill_level=skill_level,
            disabled_exp_ids=disabled_exp_ids,
        )
    )


async def _generate_resume_keyphrases_async(
    session_factory,
    *,
    user_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
    extra_keywords: list[str] | None = None,
    secondary_keywords: list[str] | None = None,
    resume_id: int | None = None,
    job_title: str | None = None,
    skill_level: str | None = None,
    disabled_exp_ids: list[int] | None = None,
) -> dict:
    from src.repositories.resume import ResumeRepository
    from src.repositories.work_experience import WorkExperienceRepository
    from src.services.ai.client import AIClient
    from src.services.ai.prompts import WorkExperienceEntry, build_per_company_key_phrases_prompt
    from src.worker.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker("resume_keyphrases")
    if not cb.is_call_allowed():
        logger.warning("Circuit breaker open, skipping resume keyphrases", user_id=user_id)
        return {"status": "circuit_open"}

    disabled_set = set(disabled_exp_ids or [])

    async with session_factory() as session:
        repo = WorkExperienceRepository(session)
        all_experiences = await repo.get_active_by_user(user_id)

    experiences = [e for e in all_experiences if e.id not in disabled_set]

    if not experiences:
        return {"status": "no_experiences"}

    # Pre-generate achievements for any experience that is missing them
    experiences = await _ensure_achievements(session_factory, experiences, locale)

    if extra_keywords:
        main_keywords = extra_keywords
    else:
        all_terms: list[str] = []
        seen: set[str] = set()
        for exp in experiences:
            if exp.stack:
                for term in exp.stack.replace(";", ",").split(","):
                    term = term.strip()
                    if term and term not in seen:
                        seen.add(term)
                        all_terms.append(term)
        main_keywords = all_terms[:30]

    effective_title = (
        job_title
        or next((e.title for e in experiences if e.title), None)
        or ("Специалист" if locale == "ru" else "Specialist")
    )

    entries = [
        WorkExperienceEntry(
            company_name=e.company_name,
            stack=e.stack,
            title=e.title,
            period=e.period,
            achievements=e.achievements,
            duties=e.duties,
        )
        for e in experiences
    ]

    from src.core.i18n import get_text

    style_label = get_text("style-formal", locale)
    prompt = build_per_company_key_phrases_prompt(
        resume_title=effective_title,
        main_keywords=main_keywords,
        secondary_keywords=secondary_keywords or [],
        style=style_label,
        per_company_count=5,
        language=locale,
        work_experiences=entries,
        skill_level=skill_level,
    )

    ai_client = AIClient()
    try:
        phrases = await ai_client.generate_key_phrases(prompt)
        cb.record_success()
    except Exception as exc:
        cb.record_failure()
        logger.error("Resume key phrases generation failed", user_id=user_id, error=str(exc))
        raise

    if not phrases:
        return {"status": "empty_response"}

    # Parse and persist per-company keyphrases into the Resume record if we have one
    if resume_id:
        keyphrases_map = _parse_keyphrases_by_company(phrases)
        async with session_factory() as session:
            resume_repo = ResumeRepository(session)
            resume = await resume_repo.get_by_id(resume_id)
            if resume:
                await resume_repo.update(resume, keyphrases_by_company=keyphrases_map)
                await session.commit()

    await _notify_resume_keyphrases(
        chat_id=chat_id,
        message_id=message_id,
        phrases=phrases,
        locale=locale,
    )
    return {"status": "completed"}


async def _ensure_achievements(session_factory, experiences, locale: str):
    """Generate achievements for entries missing them, then return a refreshed list.

    Limits concurrent AI calls to 3 via semaphore and wraps the batch with
    a circuit breaker to prevent cascading failures.
    """
    import asyncio

    from src.repositories.work_experience import WorkExperienceRepository
    from src.services.ai.client import AIClient
    from src.services.ai.prompts import (
        build_work_experience_achievements_prompt,
        build_work_experience_achievements_system_prompt,
    )
    from src.worker.circuit_breaker import CircuitBreaker

    missing = [e for e in experiences if not e.achievements]
    if not missing:
        return experiences

    cb = CircuitBreaker("work_experience_ensure_achievements")
    if not cb.is_call_allowed():
        logger.warning("Circuit breaker open for _ensure_achievements, skipping auto-generation")
        return experiences

    ai_client = AIClient()
    semaphore = asyncio.Semaphore(3)
    system_prompt = build_work_experience_achievements_system_prompt()

    async def _generate_one(exp) -> None:
        async with semaphore:
            prompt = build_work_experience_achievements_prompt(
                exp.company_name, exp.stack, title=exp.title, period=exp.period
            )
            try:
                generated = await ai_client.generate_text(
                    prompt,
                    system_prompt=system_prompt,
                    max_tokens=600,
                    temperature=0.6,
                )
                if generated:
                    async with session_factory() as session:
                        repo = WorkExperienceRepository(session)
                        fresh = await repo.get_by_id(exp.id)
                        if fresh and fresh.user_id == exp.user_id:
                            await repo.update(fresh, achievements=generated)
                            await session.commit()
                cb.record_success()
            except Exception as exc:
                cb.record_failure()
                logger.warning(
                    "Failed to auto-generate achievements",
                    work_exp_id=exp.id,
                    error=str(exc),
                )

    await asyncio.gather(*[_generate_one(exp) for exp in missing], return_exceptions=True)

    # Reload refreshed experiences from DB
    async with session_factory() as session:
        repo = WorkExperienceRepository(session)
        ids = [e.id for e in experiences]
        refreshed = []
        for exp_id in ids:
            exp = await repo.get_by_id(exp_id)
            if exp:
                refreshed.append(exp)
    return refreshed


async def _notify_resume_keyphrases(
    *,
    chat_id: int,
    message_id: int,
    phrases: str,
    locale: str,
) -> None:
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.bot.modules.resume.callbacks import ResumeCallback
    from src.config import settings
    from src.core.i18n import get_text

    header = get_text("res-keyphrases-ready", locale)
    text = f"{header}\n\n{phrases}"
    if len(text) > 4096:
        text = text[:4096]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_text("res-btn-continue-step3", locale),
                    callback_data=ResumeCallback(action="step3_summary").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_text("btn-cancel", locale),
                    callback_data=ResumeCallback(action="cancel").pack(),
                )
            ],
        ]
    )

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=keyboard,
            )
        except TelegramBadRequest:
            await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
    finally:
        await bot.session.close()
