"""Celery tasks for the achievement generation feature."""

from __future__ import annotations

import re

from src.core.constants import AppSettingKey
from src.core.logging import get_logger
from src.worker.app import celery_app
from src.worker.base_task import HHBotTask
from src.worker.utils import run_async

logger = get_logger(__name__)

_ACH_BLOCK_RE = re.compile(
    r"\[AchStart\]:(.+?)\n(.*?)\[AchEnd\]:\1",
    re.DOTALL,
)


def _parse_achievement_blocks(text: str) -> dict[str, str]:
    """Parse AI response into {company_name: achievement_text} mapping."""
    matches = _ACH_BLOCK_RE.finditer(text)
    return {m.group(1).strip(): m.group(2).strip() for m in matches}


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="achievements.generate",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=240,
    time_limit=300,
)
def generate_achievements_task(
    self,
    generation_id: int,
    chat_id: int,
    message_id: int,
    locale: str = "ru",
) -> dict:
    return run_async(
        lambda sf: _generate_achievements_async(
            self, sf, generation_id, chat_id, message_id, locale
        )
    )


async def _generate_achievements_async(
    task: HHBotTask,
    session_factory,
    generation_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
) -> dict:
    from src.models.achievement import GenerationStatus
    from src.repositories.achievement import (
        AchievementGenerationRepository,
        AchievementItemRepository,
    )
    from src.services.ai.client import AIClient
    from src.services.ai.prompts import (
        AchievementExperienceEntry,
        build_achievement_generation_prompt,
    )

    enabled = await task.check_enabled(AppSettingKey.TASK_ACHIEVEMENTS_ENABLED, session_factory)
    if not enabled:
        return {"status": "disabled"}

    cb = await task.load_circuit_breaker(
        "achievements",
        AppSettingKey.CB_ACHIEVEMENTS_FAILURE_THRESHOLD,
        AppSettingKey.CB_ACHIEVEMENTS_RECOVERY_TIMEOUT,
        session_factory,
    )
    if not cb.is_call_allowed():
        return {"status": "circuit_open"}

    idempotency_key = f"generate_achievements:{generation_id}"
    if await task.is_already_completed(idempotency_key, session_factory):
        return {"status": "already_completed"}

    async with session_factory() as session:
        gen_repo = AchievementGenerationRepository(session)
        generation = await gen_repo.get_by_id(generation_id)
        if not generation:
            return {"status": "not_found"}

        await gen_repo.update_status(generation, GenerationStatus.PROCESSING)
        await session.commit()

        items = generation.items

    entries = [
        AchievementExperienceEntry(
            company_name=item.company_name,
            stack=_get_stack(item),
            user_achievements=item.user_achievements_input,
            user_responsibilities=item.user_responsibilities_input,
        )
        for item in items
    ]

    prompt = build_achievement_generation_prompt(entries)
    ai_client = AIClient()

    try:
        response = await ai_client.generate_text(prompt)
        blocks = _parse_achievement_blocks(response)
        cb.record_success()
    except Exception as exc:
        cb.record_failure()
        async with session_factory() as session:
            gen_repo = AchievementGenerationRepository(session)
            generation = await gen_repo.get_by_id(generation_id)
            if generation:
                await gen_repo.update_status(generation, GenerationStatus.FAILED)
                await session.commit()
        logger.error("Achievement generation failed", generation_id=generation_id, error=str(exc))
        raise

    async with session_factory() as session:
        gen_repo = AchievementGenerationRepository(session)
        item_repo = AchievementItemRepository(session)
        generation = await gen_repo.get_by_id(generation_id)
        if not generation:
            return {"status": "not_found"}

        for item in generation.items:
            generated = blocks.get(item.company_name, "")
            await item_repo.update_generated_text(item, generated)

        await gen_repo.update_status(generation, GenerationStatus.COMPLETED)
        user_id = generation.user_id
        await session.commit()

    await _notify_user(task, chat_id, message_id, generation_id, locale)
    await task.mark_completed(idempotency_key, "achievements", user_id, session_factory)
    return {"status": "completed", "generation_id": generation_id}


def _get_stack(item) -> str:
    if item.work_experience and item.work_experience.stack:
        return item.work_experience.stack
    return ""


async def _notify_user(
    task: HHBotTask,
    chat_id: int,
    message_id: int,
    generation_id: int,
    locale: str,
) -> None:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.bot.modules.achievements.callbacks import AchievementCallback
    from src.core.i18n import get_text

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_text("ach-btn-view-result", locale),
                    callback_data=AchievementCallback(
                        action="detail", generation_id=generation_id
                    ).pack(),
                )
            ]
        ]
    )
    bot = task.create_bot()
    try:
        await task.notify_user(
            bot,
            chat_id,
            message_id,
            get_text("ach-generation-completed", locale),
            reply_markup=keyboard,
        )
    finally:
        await bot.session.close()
