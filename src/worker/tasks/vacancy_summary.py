"""Celery task for the vacancy summary (about-me) generation feature."""

from __future__ import annotations

from src.core.logging import get_logger
from src.worker.app import celery_app
from src.worker.utils import run_async

logger = get_logger(__name__)


@celery_app.task(bind=True, name="vacancy_summary.generate", max_retries=2, default_retry_delay=30)
def generate_vacancy_summary_task(
    self,
    summary_id: int,
    user_id: int,
    excluded_industries: str | None,
    location: str | None,
    remote_preference: str | None,
    additional_notes: str | None,
    chat_id: int,
    message_id: int,
    locale: str = "ru",
) -> dict:
    return run_async(
        lambda sf: _generate_summary_async(
            sf,
            summary_id,
            user_id,
            excluded_industries,
            location,
            remote_preference,
            additional_notes,
            chat_id,
            message_id,
            locale,
        )
    )


async def _generate_summary_async(
    session_factory,
    summary_id: int,
    user_id: int,
    excluded_industries: str | None,
    location: str | None,
    remote_preference: str | None,
    additional_notes: str | None,
    chat_id: int,
    message_id: int,
    locale: str,
) -> dict:
    from src.config import settings
    from src.repositories.vacancy_summary import VacancySummaryRepository
    from src.repositories.work_experience import WorkExperienceRepository
    from src.services.ai.client import AIClient
    from src.services.ai.prompts import (
        WorkExperienceEntry,
        build_vacancy_summary_system_prompt,
        build_vacancy_summary_user_content,
    )
    from src.worker.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker("vacancy_summary")
    if not cb.is_call_allowed():
        return {"status": "circuit_open"}

    async with session_factory() as session:
        we_repo = WorkExperienceRepository(session)
        raw_experiences = await we_repo.get_active_by_user(user_id)

    experiences = [
        WorkExperienceEntry(
            company_name=e.company_name,
            stack=e.stack,
            title=e.title,
            period=e.period,
            achievements=e.achievements,
            duties=e.duties,
        )
        for e in raw_experiences
    ]

    from src.bot.modules.autoparse.services import derive_tech_stack_from_experiences

    tech_stack = derive_tech_stack_from_experiences(raw_experiences)

    ai_client = AIClient()
    system_prompt = build_vacancy_summary_system_prompt()
    user_content = build_vacancy_summary_user_content(
        work_experiences=experiences,
        tech_stack=tech_stack,
        excluded_industries=excluded_industries,
        location=location,
        remote_preference=remote_preference,
        additional_notes=additional_notes,
    )

    try:
        response = await ai_client._client.chat.completions.create(
            model=ai_client._model,
            timeout=180,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=2000,
            temperature=0.6,
        )
        generated_text = (response.choices[0].message.content or "").strip()
        cb.record_success()
    except Exception as exc:
        cb.record_failure()
        logger.error("Vacancy summary generation failed", summary_id=summary_id, error=str(exc))
        raise

    async with session_factory() as session:
        repo = VacancySummaryRepository(session)
        summary = await repo.get_by_id(summary_id)
        if summary:
            await repo.update_text(summary, generated_text)
            await session.commit()

    await _notify_user(settings.bot_token, chat_id, message_id, summary_id, locale)
    return {"status": "completed", "summary_id": summary_id}


async def _notify_user(
    bot_token: str,
    chat_id: int,
    message_id: int,
    summary_id: int,
    locale: str,
) -> None:
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.bot.modules.vacancy_summary.callbacks import VacancySummaryCallback
    from src.core.i18n import get_text

    bot = Bot(token=bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_text("vs-btn-view", locale),
                    callback_data=VacancySummaryCallback(
                        action="detail", summary_id=summary_id
                    ).pack(),
                )
            ]
        ]
    )
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=get_text("vs-generation-completed", locale),
            reply_markup=keyboard,
        )
    except Exception:
        await bot.send_message(
            chat_id=chat_id,
            text=get_text("vs-generation-completed", locale),
            reply_markup=keyboard,
        )
    finally:
        await bot.session.close()
