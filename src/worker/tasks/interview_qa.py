"""Celery tasks for the standard interview Q&A feature."""

from __future__ import annotations

import re

from src.core.logging import get_logger
from src.worker.app import celery_app
from src.worker.utils import run_async

logger = get_logger(__name__)

_QA_BLOCK_RE = re.compile(
    r"\[QAStart\]:(\w+)\n(.*?)\[QAEnd\]:\1",
    re.DOTALL,
)


def _parse_qa_blocks(text: str) -> dict[str, str]:
    """Parse AI response into {question_key: answer_text} mapping."""
    return {m.group(1).strip(): m.group(2).strip() for m in _QA_BLOCK_RE.finditer(text)}


@celery_app.task(bind=True, name="interview_qa.generate", max_retries=2, default_retry_delay=30)
def generate_interview_qa_task(
    self,
    user_id: int,
    chat_id: int,
    message_id: int,
    locale: str = "ru",
) -> dict:
    return run_async(lambda sf: _generate_qa_async(sf, user_id, chat_id, message_id, locale))


async def _generate_qa_async(
    session_factory,
    user_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
) -> dict:
    from src.config import settings
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
    from src.worker.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker("interview_qa")
    if not cb.is_call_allowed():
        return {"status": "circuit_open"}

    async with session_factory() as session:
        we_repo = WorkExperienceRepository(session)
        work_experiences_raw = await we_repo.get_active_by_user(user_id)

        qa_repo = StandardQuestionRepository(session)
        existing_keys = {q.question_key for q in await qa_repo.get_ai_generated(user_id)}

    ai_question_keys = [k for k in BASE_QUESTION_KEYS if k != "why_new_job"]
    keys_to_generate = [k for k in ai_question_keys if k not in existing_keys]

    if not keys_to_generate:
        await _notify_user(settings.bot_token, chat_id, message_id, locale)
        return {"status": "already_generated"}

    experiences = [
        WorkExperienceEntry(company_name=e.company_name, stack=e.stack)
        for e in work_experiences_raw
    ]

    from src.core.i18n import get_text

    question_texts = [get_text(f"iqa-question-{key}", locale) for key in keys_to_generate]

    ai_client = AIClient()
    system_prompt = build_standard_qa_system_prompt()
    user_content = build_standard_qa_user_content(experiences, keys_to_generate, question_texts)

    try:
        response = await ai_client._client.chat.completions.create(
            model=ai_client._model,
            timeout=180,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=4000,
            temperature=0.5,
        )
        raw = (response.choices[0].message.content or "").strip()
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

    await _notify_user(settings.bot_token, chat_id, message_id, locale)
    return {"status": "completed"}


async def _notify_user(bot_token: str, chat_id: int, message_id: int, locale: str) -> None:
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.bot.modules.interview_qa.callbacks import InterviewQACallback
    from src.core.i18n import get_text

    bot = Bot(token=bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
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
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=get_text("iqa-generation-completed", locale),
            reply_markup=keyboard,
        )
    except Exception:
        await bot.send_message(
            chat_id=chat_id,
            text=get_text("iqa-generation-completed", locale),
            reply_markup=keyboard,
        )
    finally:
        await bot.session.close()
