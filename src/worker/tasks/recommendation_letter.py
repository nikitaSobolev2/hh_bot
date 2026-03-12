"""Celery task for AI generation of recommendation letters."""

from __future__ import annotations

from src.core.logging import get_logger
from src.worker.app import celery_app
from src.worker.utils import run_async

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    name="recommendation_letter.generate",
    max_retries=1,
    default_retry_delay=30,
    soft_time_limit=180,
    time_limit=240,
)
def generate_recommendation_letter_task(
    self,
    letter_id: int,
    user_id: int,
    chat_id: int,
    message_id: int,
    locale: str = "ru",
    next_work_exp_id: int | None = None,
    resume_id: int | None = None,
) -> dict:
    return run_async(
        lambda sf: _generate_letter_async(
            sf,
            letter_id=letter_id,
            user_id=user_id,
            chat_id=chat_id,
            message_id=message_id,
            locale=locale,
            next_work_exp_id=next_work_exp_id,
            resume_id=resume_id,
        )
    )


async def _generate_letter_async(
    session_factory,
    *,
    letter_id: int,
    user_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
    next_work_exp_id: int | None,
    resume_id: int | None,
) -> dict:
    from src.repositories.recommendation_letter import RecommendationLetterRepository
    from src.repositories.work_experience import WorkExperienceRepository
    from src.services.ai.client import AIClient
    from src.services.ai.prompts import build_recommendation_letter_prompt
    from src.worker.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker("recommendation_letter")
    if not cb.is_call_allowed():
        logger.warning("Circuit breaker open, skipping rec letter", user_id=user_id)
        return {"status": "circuit_open"}

    async with session_factory() as session:
        letter_repo = RecommendationLetterRepository(session)
        letter = await letter_repo.get_by_id(letter_id)
        if not letter:
            return {"status": "not_found"}

        we_repo = WorkExperienceRepository(session)
        exp = await we_repo.get_by_id(letter.work_experience_id)
        if not exp:
            return {"status": "work_exp_not_found"}

    prompt = build_recommendation_letter_prompt(
        company_name=exp.company_name,
        stack=exp.stack,
        speaker_name=letter.speaker_name,
        speaker_position=letter.speaker_position,
        character_key=letter.character,
        language=locale,
        title=exp.title,
        period=exp.period,
        achievements=exp.achievements,
        duties=exp.duties,
        focus_text=letter.focus_text,
    )

    ai_client = AIClient()
    try:
        generated = await ai_client.generate_text(prompt, max_tokens=800, temperature=0.65)
        cb.record_success()
    except Exception as exc:
        cb.record_failure()
        logger.error(
            "Recommendation letter generation failed",
            letter_id=letter_id,
            error=str(exc),
        )
        raise

    async with session_factory() as session:
        letter_repo = RecommendationLetterRepository(session)
        fresh_letter = await letter_repo.get_by_id(letter_id)
        if fresh_letter:
            await letter_repo.update_generated_text(fresh_letter, generated or "")
            await session.commit()

    await _notify_user(
        chat_id=chat_id,
        message_id=message_id,
        letter_id=letter_id,
        locale=locale,
        next_work_exp_id=next_work_exp_id,
        resume_id=resume_id,
    )
    return {"status": "completed", "letter_id": letter_id}


async def _notify_user(
    *,
    chat_id: int,
    message_id: int,
    letter_id: int,
    locale: str,
    next_work_exp_id: int | None,
    resume_id: int | None,
) -> None:
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.bot.modules.resume.callbacks import ResumeCallback
    from src.config import settings
    from src.core.i18n import get_text

    rows: list[list[InlineKeyboardButton]] = []

    if next_work_exp_id:
        rows.append(
            [
                InlineKeyboardButton(
                    text=get_text("res-btn-next-job-letter", locale),
                    callback_data=ResumeCallback(
                        action="rec_next",
                        work_exp_id=next_work_exp_id,
                    ).pack(),
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text=get_text("res-btn-show-result", locale),
                    callback_data=ResumeCallback(action="show_result").pack(),
                )
            ]
        )

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    text = get_text("res-rec-letter-ready", locale)
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
