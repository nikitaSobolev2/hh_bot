"""Celery tasks for the interview preparation feature."""

from __future__ import annotations

import re

from src.core.logging import get_logger
from src.worker.app import celery_app
from src.worker.utils import run_async

logger = get_logger(__name__)

_PREP_STEP_RE = re.compile(
    r"\[PrepStepStart\]:(\d+):(.+?)\n(.*?)\[PrepStepEnd\]:\1:",
    re.DOTALL,
)

_TEST_Q_RE = re.compile(r"\[Q\]:(.+?)(?=\[Q\]|\[TestEnd\])", re.DOTALL)
_TEST_A_RE = re.compile(r"\[A\]:(.+)")


def _parse_prep_steps(text: str) -> list[dict]:
    steps = []
    for m in _PREP_STEP_RE.finditer(text):
        steps.append(
            {
                "step_number": int(m.group(1)),
                "title": m.group(2).strip(),
                "content": m.group(3).strip(),
            }
        )
    return steps


def _parse_test_questions(text: str) -> list[dict]:
    questions = []
    for qm in _TEST_Q_RE.finditer(text):
        q_text = qm.group(1).strip().split("\n")[0].strip()
        block = qm.group(0)
        options = []
        correct_index = 0
        for i, am in enumerate(_TEST_A_RE.finditer(block)):
            opt = am.group(1).strip()
            if opt.endswith("*"):
                correct_index = i
                opt = opt[:-1].strip()
            options.append(opt)
        questions.append({"question": q_text, "options": options, "correct_index": correct_index})
    return questions


@celery_app.task(
    bind=True,
    name="interviews.generate_preparation",
    max_retries=2,
    default_retry_delay=30,
)
def generate_preparation_task(
    self,
    interview_id: int,
    chat_id: int,
    message_id: int,
    locale: str = "ru",
) -> dict:
    return run_async(
        lambda sf: _generate_preparation_async(sf, interview_id, chat_id, message_id, locale)
    )


async def _generate_preparation_async(
    session_factory,
    interview_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
) -> dict:
    from src.config import settings
    from src.models.interview import InterviewPreparationStep
    from src.repositories.interview import InterviewRepository
    from src.repositories.work_experience import WorkExperienceRepository
    from src.services.ai.client import AIClient
    from src.services.ai.prompts import build_preparation_guide_prompt
    from src.worker.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker("interview_prep")
    if not cb.is_call_allowed():
        return {"status": "circuit_open"}

    async with session_factory() as session:
        interview_repo = InterviewRepository(session)
        interview = await interview_repo.get_by_id(interview_id)
        if not interview:
            return {"status": "not_found"}

        we_repo = WorkExperienceRepository(session)
        experiences = await we_repo.get_active_by_user(interview.user_id)

    tech_stack = [e.stack for e in experiences] if experiences else []

    def _fmt_exp(e) -> str:
        parts = [e.company_name]
        if e.title:
            parts.append(f"— {e.title}")
        if e.period:
            parts.append(f"({e.period})")
        parts.append(f"[{e.stack}]")
        return " ".join(parts)

    work_exp_str = "; ".join(_fmt_exp(e) for e in experiences) if experiences else "не указан"

    prompt = build_preparation_guide_prompt(
        vacancy_title=interview.vacancy_title,
        vacancy_description=interview.vacancy_description,
        user_tech_stack=tech_stack,
        user_work_experience=work_exp_str,
    )
    ai_client = AIClient()

    try:
        response_text = await ai_client.generate_text(prompt, max_tokens=4000)
        steps_data = _parse_prep_steps(response_text)
        cb.record_success()
    except Exception as exc:
        cb.record_failure()
        logger.error(
            "Preparation guide generation failed",
            interview_id=interview_id,
            error=str(exc),
        )
        raise

    async with session_factory() as session:
        for step_data in steps_data:
            step = InterviewPreparationStep(
                interview_id=interview_id,
                step_number=step_data["step_number"],
                title=step_data["title"],
                content=step_data["content"],
            )
            session.add(step)
        await session.commit()

    await _notify_user_prep(settings.bot_token, chat_id, message_id, interview_id, locale)
    return {"status": "completed", "steps_count": len(steps_data)}


@celery_app.task(
    bind=True,
    name="interviews.generate_deep_summary",
    max_retries=2,
    default_retry_delay=30,
)
def generate_deep_summary_task(
    self,
    step_id: int,
    interview_id: int,
    chat_id: int,
    message_id: int,
    locale: str = "ru",
) -> dict:
    return run_async(
        lambda sf: _generate_deep_summary_async(
            sf, step_id, interview_id, chat_id, message_id, locale
        )
    )


async def _generate_deep_summary_async(
    session_factory,
    step_id: int,
    interview_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
) -> dict:
    from src.config import settings
    from src.repositories.interview import InterviewPreparationRepository
    from src.services.ai.client import AIClient
    from src.services.ai.prompts import build_deep_learning_summary_prompt
    from src.worker.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker("interview_deep_summary")
    if not cb.is_call_allowed():
        return {"status": "circuit_open"}

    async with session_factory() as session:
        prep_repo = InterviewPreparationRepository(session)
        step = await prep_repo.get_step_by_id(step_id)
        if not step:
            return {"status": "not_found"}
        interview = step.interview
        vacancy_context = f"{interview.vacancy_title}"
        if interview.vacancy_description:
            vacancy_context += f"\n{interview.vacancy_description[:500]}"

    ai_client = AIClient()
    prompt = build_deep_learning_summary_prompt(
        step_title=step.title,
        step_content=step.content,
        vacancy_context=vacancy_context,
    )

    try:
        deep_summary = await ai_client.generate_text(prompt, max_tokens=2000)
        cb.record_success()
    except Exception as exc:
        cb.record_failure()
        logger.error("Deep summary generation failed", step_id=step_id, error=str(exc))
        raise

    async with session_factory() as session:
        prep_repo = InterviewPreparationRepository(session)
        await prep_repo.update_step_deep_summary(step_id, deep_summary)
        await prep_repo.update_step_status(step_id, "completed")
        await session.commit()

    await _notify_user_deep_summary(
        settings.bot_token, chat_id, message_id, step_id, interview_id, locale
    )
    return {"status": "completed"}


@celery_app.task(
    bind=True,
    name="interviews.generate_test",
    max_retries=2,
    default_retry_delay=30,
)
def generate_test_task(
    self,
    step_id: int,
    interview_id: int,
    chat_id: int,
    message_id: int,
    locale: str = "ru",
) -> dict:
    return run_async(
        lambda sf: _generate_test_async(sf, step_id, interview_id, chat_id, message_id, locale)
    )


async def _generate_test_async(
    session_factory,
    step_id: int,
    interview_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
) -> dict:
    from src.config import settings
    from src.models.interview import InterviewPreparationTest
    from src.repositories.interview import InterviewPreparationRepository
    from src.services.ai.client import AIClient
    from src.services.ai.prompts import build_preparation_test_prompt
    from src.worker.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker("interview_test")
    if not cb.is_call_allowed():
        return {"status": "circuit_open"}

    async with session_factory() as session:
        prep_repo = InterviewPreparationRepository(session)
        step = await prep_repo.get_step_by_id(step_id)
        if not step:
            return {"status": "not_found"}

    ai_client = AIClient()
    prompt = build_preparation_test_prompt(
        step_title=step.title,
        step_content=step.content,
        deep_summary=step.deep_summary,
    )

    try:
        response_text = await ai_client.generate_text(prompt, max_tokens=2000)
        questions = _parse_test_questions(response_text)
        cb.record_success()
    except Exception as exc:
        cb.record_failure()
        logger.error("Test generation failed", step_id=step_id, error=str(exc))
        raise

    async with session_factory() as session:
        existing_test = await session.get(InterviewPreparationTest, {"step_id": step_id})
        if existing_test:
            existing_test.questions_json = {"questions": questions}
            existing_test.user_answers_json = None
        else:
            test = InterviewPreparationTest(
                step_id=step_id,
                questions_json={"questions": questions},
            )
            session.add(test)
        await session.commit()

    await _notify_user_test_ready(
        settings.bot_token, chat_id, message_id, step_id, interview_id, locale
    )
    return {"status": "completed", "questions_count": len(questions)}


async def _notify_user_prep(
    bot_token: str,
    chat_id: int,
    message_id: int,
    interview_id: int,
    locale: str,
) -> None:
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.bot.modules.interviews.callbacks import InterviewCallback
    from src.core.i18n import get_text

    bot = Bot(token=bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_text("prep-btn-view-steps", locale),
                    callback_data=InterviewCallback(
                        action="prep_steps", interview_id=interview_id
                    ).pack(),
                )
            ]
        ]
    )
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=get_text("prep-guide-completed", locale),
            reply_markup=keyboard,
        )
    except Exception:
        await bot.send_message(
            chat_id=chat_id,
            text=get_text("prep-guide-completed", locale),
            reply_markup=keyboard,
        )
    finally:
        await bot.session.close()


async def _notify_user_deep_summary(
    bot_token: str,
    chat_id: int,
    message_id: int,
    step_id: int,
    interview_id: int,
    locale: str,
) -> None:
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.bot.modules.interviews.callbacks import InterviewCallback
    from src.core.i18n import get_text

    bot = Bot(token=bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_text("prep-btn-view-deep", locale),
                    callback_data=InterviewCallback(
                        action="prep_step_deep",
                        interview_id=interview_id,
                        prep_step_id=step_id,
                    ).pack(),
                )
            ]
        ]
    )
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=get_text("prep-deep-completed", locale),
            reply_markup=keyboard,
        )
    except Exception:
        await bot.send_message(
            chat_id=chat_id,
            text=get_text("prep-deep-completed", locale),
            reply_markup=keyboard,
        )
    finally:
        await bot.session.close()


async def _notify_user_test_ready(
    bot_token: str,
    chat_id: int,
    message_id: int,
    step_id: int,
    interview_id: int,
    locale: str,
) -> None:
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.bot.modules.interviews.callbacks import InterviewCallback
    from src.core.i18n import get_text

    bot = Bot(token=bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_text("prep-btn-start-test", locale),
                    callback_data=InterviewCallback(
                        action="prep_test",
                        interview_id=interview_id,
                        prep_step_id=step_id,
                        test_q_index=0,
                    ).pack(),
                )
            ]
        ]
    )
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=get_text("prep-test-ready", locale),
            reply_markup=keyboard,
        )
    except Exception:
        await bot.send_message(
            chat_id=chat_id,
            text=get_text("prep-test-ready", locale),
            reply_markup=keyboard,
        )
    finally:
        await bot.session.close()
