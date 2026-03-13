"""Celery task for AI generation of recommendation letters."""

from __future__ import annotations

from src.core.logging import get_logger
from src.worker.app import celery_app
from src.worker.base_task import HHBotTask
from src.worker.utils import run_async

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    base=HHBotTask,
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
            self,
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
    task: HHBotTask,
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
    from celery.exceptions import SoftTimeLimitExceeded

    from src.core.constants import AppSettingKey
    from src.core.i18n import get_text
    from src.repositories.recommendation_letter import RecommendationLetterRepository
    from src.repositories.work_experience import WorkExperienceRepository
    from src.services.ai.client import AIClient
    from src.services.ai.prompts import (
        build_recommendation_letter_prompt,
        build_recommendation_letter_system_prompt,
    )

    enabled = await task.check_enabled(
        AppSettingKey.TASK_RECOMMENDATION_LETTER_ENABLED, session_factory
    )
    if not enabled:
        return {"status": "disabled"}

    cb = await task.load_circuit_breaker(
        "recommendation_letter",
        AppSettingKey.CB_RECOMMENDATION_LETTER_FAILURE_THRESHOLD,
        AppSettingKey.CB_RECOMMENDATION_LETTER_RECOVERY_TIMEOUT,
        session_factory,
    )
    if not cb.is_call_allowed():
        logger.warning("Circuit breaker open, skipping rec letter", user_id=user_id)
        return {"status": "circuit_open"}

    idempotency_key = f"rec_letter:{letter_id}"
    if await task.is_already_completed(idempotency_key, session_factory):
        return {"status": "already_completed"}

    bot = task.create_bot()

    try:
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
        system_prompt = build_recommendation_letter_system_prompt(language=locale)

        ai_client = AIClient()
        try:
            generated = await ai_client.generate_text(
                prompt, system_prompt=system_prompt, max_tokens=800, temperature=0.65
            )
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
            task=task,
            bot=bot,
            chat_id=chat_id,
            message_id=message_id,
            letter_id=letter_id,
            locale=locale,
            next_work_exp_id=next_work_exp_id,
            resume_id=resume_id,
        )
        await task.mark_completed(idempotency_key, "rec_letter", user_id, session_factory)
        return {"status": "completed", "letter_id": letter_id}

    except SoftTimeLimitExceeded:
        await task.handle_soft_timeout(bot, chat_id, message_id, locale)
        task.request.retries = task.max_retries
        raise

    except Exception as exc:
        logger.error("Recommendation letter task failed", letter_id=letter_id, error=str(exc))
        if task.request.retries >= task.max_retries:
            await task.notify_user(
                bot, chat_id, message_id, get_text("res-rec-letter-failed", locale)
            )
        raise task.retry(exc=exc) from exc

    finally:
        await bot.session.close()


async def _notify_user(
    *,
    task: HHBotTask,
    bot,
    chat_id: int,
    message_id: int,
    letter_id: int,
    locale: str,
    next_work_exp_id: int | None,
    resume_id: int | None,
) -> None:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.bot.modules.resume.callbacks import ResumeCallback
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
    await task.notify_user(
        bot,
        chat_id,
        message_id,
        get_text("res-rec-letter-ready", locale),
        reply_markup=keyboard,
    )
