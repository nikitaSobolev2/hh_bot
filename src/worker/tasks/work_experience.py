"""Celery task for AI generation of work experience achievements and duties."""

from __future__ import annotations

from celery.exceptions import SoftTimeLimitExceeded

from src.core.constants import AppSettingKey, TaskName
from src.core.logging import get_logger
from src.worker.app import celery_app
from src.worker.base_task import HHBotTask
from src.worker.utils import run_async

logger = get_logger(__name__)

_IMPROVE_STACK_MAX_OUT_LEN = 8000

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
    reference_text: str | None = None,
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
            reference_text=reference_text,
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
    reference_text: str | None = None,
) -> dict:
    from src.services.ai.client import AIClient, close_ai_client
    from src.worker.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker("work_experience_ai")
    if not cb.is_call_allowed():
        logger.warning("Circuit breaker open, skipping WE AI generation", user_id=user_id)
        return {"status": "circuit_open"}

    existing_achievements: str | None = None
    existing_duties: str | None = None
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
            existing_achievements = exp.achievements
            existing_duties = exp.duties

    prompt, system_prompt = _build_prompt(
        field,
        company_name,
        stack,
        title,
        period,
        reference_text=reference_text,
        existing_achievements=existing_achievements,
        existing_duties=existing_duties,
    )
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
    finally:
        await close_ai_client(ai_client)

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


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="work_experience.improve_stack",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=240,
    time_limit=300,
)
def improve_work_experience_stack_task(
    self,
    user_id: int,
    chat_id: int,
    message_id: int,
    work_exp_id: int,
    locale: str = "ru",
    return_to: str = "menu",
) -> dict:
    try:
        return run_async(
            lambda sf: _improve_stack_async(
                self,
                sf,
                user_id=user_id,
                chat_id=chat_id,
                message_id=message_id,
                work_exp_id=work_exp_id,
                locale=locale,
                return_to=return_to,
            )
        )
    except SoftTimeLimitExceeded:
        logger.warning(
            "improve_stack soft time limit exceeded",
            user_id=user_id,
            work_exp_id=work_exp_id,
        )
        idempotency_key = f"improve_we_stack:{self.request.id}"
        try:
            run_async(
                lambda sf: _improve_stack_soft_timeout_async(
                    self,
                    sf,
                    user_id=user_id,
                    chat_id=chat_id,
                    message_id=message_id,
                    locale=locale,
                    idempotency_key=idempotency_key,
                )
            )
        except Exception:
            logger.exception("improve_stack soft timeout cleanup failed")
        self.request.retries = self.max_retries
        raise


async def _improve_stack_soft_timeout_async(
    task: HHBotTask,
    session_factory,
    *,
    user_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
    idempotency_key: str,
) -> None:
    bot = task.create_bot()
    try:
        await task.handle_soft_timeout(
            bot,
            chat_id,
            message_id,
            locale,
            idempotency_key=idempotency_key,
            task_type="work_experience_improve_stack",
            user_id=user_id,
            session_factory=session_factory,
        )
    finally:
        await bot.session.close()


async def _improve_stack_async(
    task: HHBotTask,
    session_factory,
    *,
    user_id: int,
    chat_id: int,
    message_id: int,
    work_exp_id: int,
    locale: str,
    return_to: str,
) -> dict:
    from src.repositories.work_experience import WorkExperienceRepository
    from src.services.ai.client import AIClient, close_ai_client
    from src.services.ai.prompts import (
        build_improve_stack_system_prompt,
        build_improve_stack_user_prompt,
        normalize_improved_stack_output,
        ordered_unique_stack_tokens,
    )

    enabled = await task.check_enabled(
        AppSettingKey.TASK_WORK_EXPERIENCE_AI_ENABLED,
        session_factory,
    )
    if not enabled:
        return {"status": "disabled"}

    cb = await task.load_circuit_breaker(
        "work_experience_improve_stack",
        AppSettingKey.CB_WORK_EXPERIENCE_AI_FAILURE_THRESHOLD,
        AppSettingKey.CB_WORK_EXPERIENCE_AI_RECOVERY_TIMEOUT,
        session_factory,
    )
    if not cb.is_call_allowed():
        logger.warning("Circuit breaker open, skipping improve stack", user_id=user_id)
        return {"status": "circuit_open"}

    idempotency_key = f"improve_we_stack:{task.request.id}"
    if await task.is_already_completed(idempotency_key, session_factory):
        return {"status": "already_completed"}

    async with session_factory() as session:
        repo = WorkExperienceRepository(session)
        exp = await repo.get_by_id(work_exp_id)
        if not exp or exp.user_id != user_id or not exp.is_active:
            return {"status": "not_found"}

        stack_in = exp.stack or ""
        company_name = exp.company_name
        title = exp.title
        period = exp.period
        achievements = exp.achievements
        duties = exp.duties

    system_prompt = build_improve_stack_system_prompt()
    user_prompt = build_improve_stack_user_prompt(
        stack=stack_in,
        company_name=company_name,
        title=title,
        period=period,
        achievements=achievements,
        duties=duties,
        locale=locale,
    )
    ai_client = AIClient()

    try:
        generated = await ai_client.generate_text(
            user_prompt,
            system_prompt=system_prompt,
            max_tokens=400,
            temperature=0.35,
        )
        cb.record_success()
    except Exception as exc:
        cb.record_failure()
        logger.error(
            "Improve stack AI failed",
            user_id=user_id,
            work_exp_id=work_exp_id,
            error=str(exc),
        )
        raise
    finally:
        await close_ai_client(ai_client)

    improved = normalize_improved_stack_output(generated or "")
    if not improved.strip():
        improved = ordered_unique_stack_tokens(stack_in) or stack_in
    if len(improved) > _IMPROVE_STACK_MAX_OUT_LEN:
        improved = improved[: _IMPROVE_STACK_MAX_OUT_LEN - 1] + "…"

    async with session_factory() as session:
        repo = WorkExperienceRepository(session)
        exp = await repo.get_by_id(work_exp_id)
        if exp and exp.user_id == user_id:
            await repo.update(exp, stack=improved)
            await session.commit()

    bot = task.create_bot()
    try:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        from src.bot.modules.work_experience.callbacks import WorkExpCallback
        from src.core.i18n import get_text

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=get_text("we-btn-view-result", locale),
                        callback_data=WorkExpCallback(
                            action="detail",
                            work_exp_id=work_exp_id,
                            return_to=return_to,
                        ).pack(),
                    )
                ]
            ]
        )
        await task.notify_user(
            bot,
            chat_id,
            message_id,
            get_text("work-exp-ai-generation-done", locale),
            reply_markup=keyboard,
        )
    finally:
        await bot.session.close()

    await task.mark_completed(
        idempotency_key,
        "work_experience_improve_stack",
        user_id,
        session_factory,
        result_data={
            "task": str(TaskName.IMPROVE_WORK_EXPERIENCE_STACK),
            "work_exp_id": work_exp_id,
        },
    )
    return {"status": "completed", "work_exp_id": work_exp_id}


def _build_prompt(
    field: str,
    company_name: str,
    stack: str,
    title: str | None,
    period: str | None,
    *,
    reference_text: str | None = None,
    existing_achievements: str | None = None,
    existing_duties: str | None = None,
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
                company_name,
                stack,
                title=title,
                period=period,
                reference_text=reference_text,
                existing_achievements=existing_achievements,
                existing_duties=existing_duties,
            ),
            build_work_experience_achievements_system_prompt(),
        )
    return (
        build_work_experience_duties_prompt(
            company_name,
            stack,
            title=title,
            period=period,
            reference_text=reference_text,
            existing_achievements=existing_achievements,
            existing_duties=existing_duties,
        ),
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
    from src.services.ai.client import AIClient, close_ai_client
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
    finally:
        await close_ai_client(ai_client)

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
    from src.services.ai.client import AIClient, close_ai_client
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

    try:
        await asyncio.gather(*[_generate_one(exp) for exp in missing], return_exceptions=True)
    finally:
        await close_ai_client(ai_client)

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
