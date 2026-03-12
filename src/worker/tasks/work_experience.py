"""Celery task for AI generation of work experience achievements and duties."""

from __future__ import annotations

from src.core.logging import get_logger
from src.worker.app import celery_app
from src.worker.utils import run_async

logger = get_logger(__name__)

_MODE_CREATE = "create"
_MODE_EDIT = "edit"


@celery_app.task(
    bind=True,
    name="work_experience.generate_ai",
    max_retries=2,
    default_retry_delay=30,
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

    prompt = _build_prompt(field, company_name, stack, title, period)
    ai_client = AIClient()

    try:
        generated = await ai_client.generate_text(prompt, max_tokens=800, temperature=0.6)
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
) -> str:
    from src.services.ai.prompts import (
        build_work_experience_achievements_prompt,
        build_work_experience_duties_prompt,
    )

    if field == "achievements":
        return build_work_experience_achievements_prompt(
            company_name, stack, title=title, period=period
        )
    return build_work_experience_duties_prompt(company_name, stack, title=title, period=period)


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
