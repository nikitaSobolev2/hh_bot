"""Celery tasks for the standard interview Q&A feature."""

from __future__ import annotations

import re

import httpx

from src.core.constants import AppSettingKey
from src.core.logging import get_logger
from src.worker.app import celery_app
from src.worker.base_task import HHBotTask
from src.worker.utils import run_async

logger = get_logger(__name__)

_QA_BLOCK_RE = re.compile(
    r"\[QAStart\]:(\w+)\n(.*?)\[QAEnd\]:\1",
    re.DOTALL,
)


def _parse_qa_blocks(text: str) -> dict[str, str]:
    """Parse AI response into {question_key: answer_text} mapping."""
    return {m.group(1).strip(): m.group(2).strip() for m in _QA_BLOCK_RE.finditer(text)}


def _send_timeout_message(bot_token: str, chat_id: int, locale: str) -> None:
    """Synchronously send a timeout notification via the raw Telegram HTTP API.

    Deliberately avoids asyncio so this works reliably after a
    SoftTimeLimitExceeded interrupts a running event loop.
    """
    from src.core.i18n import get_text

    text = get_text("iqa-generation-timeout", locale)
    with httpx.Client(timeout=10) as client:
        client.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        )


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="interview_qa.generate",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=240,
    time_limit=300,
)
def generate_interview_qa_task(
    self,
    user_id: int,
    chat_id: int,
    message_id: int,
    locale: str = "ru",
    question_key: str | None = None,
) -> dict:
    from celery.exceptions import SoftTimeLimitExceeded

    from src.config import settings

    try:
        return run_async(
            lambda sf: _generate_qa_async(
                self, sf, user_id, chat_id, message_id, locale, question_key
            )
        )
    except SoftTimeLimitExceeded:
        logger.warning(
            "interview_qa.generate soft time limit exceeded",
            user_id=user_id,
            chat_id=chat_id,
        )
        _send_timeout_message(settings.bot_token, chat_id, locale)
        self.request.retries = self.max_retries
        raise


async def _generate_qa_async(
    task: HHBotTask,
    session_factory,
    user_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
    question_key: str | None = None,
) -> dict:
    from src.models.interview_qa import (
        BASE_QUESTION_KEYS,
        QuestionCategory,
    )
    from src.repositories.interview_qa import StandardQuestionRepository
    from src.repositories.work_experience import WorkExperienceRepository
    from src.services.ai.client import AIClient
    from src.services.ai.prompts import (
        WorkExperienceEntry,
        build_standard_qa_system_prompt,
        build_standard_qa_user_content,
    )

    enabled = await task.check_enabled(AppSettingKey.TASK_INTERVIEW_QA_ENABLED, session_factory)
    if not enabled:
        return {"status": "disabled"}

    idempotency_key = f"interview_qa:{user_id}:{question_key or 'all'}"
    if await task.is_already_completed(idempotency_key, session_factory):
        await _notify_user(task, chat_id, message_id, locale)
        return {"status": "already_completed"}

    cb = await task.load_circuit_breaker(
        "interview_qa",
        AppSettingKey.CB_INTERVIEW_QA_FAILURE_THRESHOLD,
        AppSettingKey.CB_INTERVIEW_QA_RECOVERY_TIMEOUT,
        session_factory,
    )
    if not cb.is_call_allowed():
        return {"status": "circuit_open"}

    async with session_factory() as session:
        we_repo = WorkExperienceRepository(session)
        work_experiences_raw = await we_repo.get_active_by_user(user_id)

        qa_repo = StandardQuestionRepository(session)
        existing_keys = {q.question_key for q in await qa_repo.get_ai_generated(user_id)}

    ai_question_keys = [k for k in BASE_QUESTION_KEYS if k != "why_new_job"]

    if question_key is not None:
        keys_to_generate = [question_key]
    else:
        keys_to_generate = [k for k in ai_question_keys if k not in existing_keys]

    if not keys_to_generate:
        await _notify_user(task, chat_id, message_id, locale)
        return {"status": "already_generated"}

    experiences = [
        WorkExperienceEntry(
            company_name=e.company_name,
            stack=e.stack,
            title=e.title,
            period=e.period,
            achievements=e.achievements,
            duties=e.duties,
        )
        for e in work_experiences_raw
    ]

    from src.core.i18n import get_text

    question_texts = [get_text(f"iqa-question-{key}", locale) for key in keys_to_generate]

    ai_client = AIClient()
    system_prompt = build_standard_qa_system_prompt()
    user_content = build_standard_qa_user_content(experiences, keys_to_generate, question_texts)

    try:
        raw = await ai_client.generate_text(
            user_content,
            system_prompt=system_prompt,
            timeout=180,
            max_tokens=4000,
            temperature=0.5,
        )
        blocks = _parse_qa_blocks(raw)
        cb.record_success()
    except Exception as exc:
        cb.record_failure()
        logger.error("Interview QA generation failed", user_id=user_id, error=str(exc))
        raise

    async with session_factory() as session:
        qa_repo = StandardQuestionRepository(session)
        for key, answer in blocks.items():
            idx = keys_to_generate.index(key) if key in keys_to_generate else -1
            q_text = question_texts[idx] if idx >= 0 else key
            await qa_repo.upsert_answer(
                user_id,
                key,
                q_text,
                answer,
                is_base_question=False,
                category=QuestionCategory.AI_GENERATED,
            )
        await session.commit()

    await _notify_user(task, chat_id, message_id, locale)
    await task.mark_completed(idempotency_key, "interview_qa", user_id, session_factory)
    return {"status": "completed"}


async def _notify_user(task: HHBotTask, chat_id: int, message_id: int, locale: str) -> None:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.bot.modules.interview_qa.callbacks import InterviewQACallback
    from src.core.i18n import get_text

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_text("iqa-btn-view", locale),
                    callback_data=InterviewQACallback(action="list").pack(),
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
            get_text("iqa-generation-completed", locale),
            reply_markup=keyboard,
        )
    finally:
        await bot.session.close()
