"""Celery tasks for the interview preparation feature."""

from __future__ import annotations

import re

from src.core.logging import get_logger
from src.worker.app import celery_app
from src.worker.base_task import HHBotTask
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
    base=HHBotTask,
    name="interviews.generate_preparation",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=300,
    time_limit=360,
)
def generate_preparation_task(
    self,
    interview_id: int,
    chat_id: int,
    message_id: int,
    locale: str = "ru",
) -> dict:
    return run_async(
        lambda sf: _generate_preparation_async(self, sf, interview_id, chat_id, message_id, locale)
    )


async def _generate_preparation_async(
    task: HHBotTask,
    session_factory,
    interview_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
) -> dict:
    from celery.exceptions import SoftTimeLimitExceeded

    from src.core.constants import AppSettingKey
    from src.core.i18n import get_text
    from src.models.interview import InterviewPreparationStep
    from src.repositories.interview import InterviewRepository
    from src.repositories.work_experience import WorkExperienceRepository
    from src.services.ai.client import AIClient
    from src.services.ai.prompts import (
        build_preparation_guide_prompt,
        build_preparation_guide_system_prompt,
    )

    enabled = await task.check_enabled(AppSettingKey.TASK_INTERVIEW_PREP_ENABLED, session_factory)
    if not enabled:
        return {"status": "disabled"}

    idempotency_key = f"interview_prep:{interview_id}"
    if await task.is_already_completed(idempotency_key, session_factory):
        return {"status": "already_completed"}

    cb = await task.load_circuit_breaker(
        "interview_prep",
        AppSettingKey.CB_PREP_GUIDE_FAILURE_THRESHOLD,
        AppSettingKey.CB_PREP_GUIDE_RECOVERY_TIMEOUT,
        session_factory,
    )
    if not cb.is_call_allowed():
        return {"status": "circuit_open"}

    bot = task.create_bot()

    try:
        async with session_factory() as session:
            interview = await InterviewRepository(session).get_by_id(interview_id)
            if not interview:
                return {"status": "not_found"}
            user_id = interview.user_id

            experiences = await WorkExperienceRepository(session).get_active_by_user(
                interview.user_id
            )

        tech_stack = [e.stack for e in experiences] if experiences else []

        from src.services.formatters import format_work_experience_block

        work_exp_str = format_work_experience_block(experiences) if experiences else "не указан"

        prompt = build_preparation_guide_prompt(
            vacancy_title=interview.vacancy_title,
            vacancy_description=interview.vacancy_description,
            user_tech_stack=tech_stack,
            user_work_experience=work_exp_str,
        )
        system_prompt = build_preparation_guide_system_prompt()
        ai_client = AIClient()

        try:
            response_text = await ai_client.generate_text(
                prompt, system_prompt=system_prompt, max_tokens=4000
            )
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

        await _notify_user_prep(task, bot, chat_id, message_id, interview_id, locale)
        await task.mark_completed(idempotency_key, "interview_prep", user_id, session_factory)
        return {"status": "completed", "steps_count": len(steps_data)}

    except SoftTimeLimitExceeded:
        await task.handle_soft_timeout(bot, chat_id, message_id, locale)
        task.request.retries = task.max_retries
        raise

    except Exception as exc:
        logger.error("Preparation task failed", interview_id=interview_id, error=str(exc))
        if task.request.retries >= task.max_retries:
            await task.notify_user(bot, chat_id, message_id, get_text("prep-guide-failed", locale))
        raise task.retry(exc=exc) from exc

    finally:
        await bot.session.close()


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="interviews.generate_deep_summary",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=240,
    time_limit=300,
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
            self, sf, step_id, interview_id, chat_id, message_id, locale
        )
    )


async def _generate_deep_summary_async(
    task: HHBotTask,
    session_factory,
    step_id: int,
    interview_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
) -> dict:
    from celery.exceptions import SoftTimeLimitExceeded

    from src.core.constants import AppSettingKey
    from src.core.i18n import get_text
    from src.repositories.interview import InterviewPreparationRepository
    from src.services.ai.client import AIClient
    from src.services.ai.prompts import (
        build_deep_learning_summary_prompt,
        build_deep_learning_summary_system_prompt,
    )

    enabled = await task.check_enabled(AppSettingKey.TASK_INTERVIEW_PREP_ENABLED, session_factory)
    if not enabled:
        return {"status": "disabled"}

    cb = await task.load_circuit_breaker(
        "interview_deep_summary",
        AppSettingKey.CB_PREP_DEEP_SUMMARY_FAILURE_THRESHOLD,
        AppSettingKey.CB_PREP_DEEP_SUMMARY_RECOVERY_TIMEOUT,
        session_factory,
    )
    if not cb.is_call_allowed():
        return {"status": "circuit_open"}

    bot = task.create_bot()

    try:
        async with session_factory() as session:
            prep_repo = InterviewPreparationRepository(session)
            step = await prep_repo.get_step_by_id(step_id)
            if not step:
                return {"status": "not_found"}
            interview = step.interview
            vacancy_context = f"{interview.vacancy_title}"
            if interview.vacancy_description:
                vacancy_context += f"\n{interview.vacancy_description[:3000]}"

        ai_client = AIClient()
        system_prompt = build_deep_learning_summary_system_prompt()
        prompt = build_deep_learning_summary_prompt(
            step_title=step.title,
            step_content=step.content,
            vacancy_context=vacancy_context,
        )

        try:
            deep_summary = await ai_client.generate_text(
                prompt, system_prompt=system_prompt, max_tokens=20000
            )
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
            task, bot, chat_id, message_id, step_id, interview_id, locale
        )
        return {"status": "completed"}

    except SoftTimeLimitExceeded:
        await task.handle_soft_timeout(bot, chat_id, message_id, locale)
        task.request.retries = task.max_retries
        raise

    except Exception as exc:
        logger.error("Deep summary task failed", step_id=step_id, error=str(exc))
        if task.request.retries >= task.max_retries:
            await task.notify_user(bot, chat_id, message_id, get_text("prep-deep-failed", locale))
        raise task.retry(exc=exc) from exc

    finally:
        await bot.session.close()


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="interviews.generate_test",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=240,
    time_limit=300,
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
        lambda sf: _generate_test_async(
            self, sf, step_id, interview_id, chat_id, message_id, locale
        )
    )


async def _generate_test_async(
    task: HHBotTask,
    session_factory,
    step_id: int,
    interview_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
) -> dict:
    from celery.exceptions import SoftTimeLimitExceeded

    from src.core.constants import AppSettingKey
    from src.core.i18n import get_text
    from src.models.interview import InterviewPreparationTest
    from src.repositories.interview import InterviewPreparationRepository
    from src.services.ai.client import AIClient
    from src.services.ai.prompts import (
        build_preparation_test_prompt,
        build_preparation_test_system_prompt,
    )

    enabled = await task.check_enabled(AppSettingKey.TASK_INTERVIEW_PREP_ENABLED, session_factory)
    if not enabled:
        return {"status": "disabled"}

    cb = await task.load_circuit_breaker(
        "interview_test",
        AppSettingKey.CB_PREP_TEST_FAILURE_THRESHOLD,
        AppSettingKey.CB_PREP_TEST_RECOVERY_TIMEOUT,
        session_factory,
    )
    if not cb.is_call_allowed():
        return {"status": "circuit_open"}

    bot = task.create_bot()

    try:
        async with session_factory() as session:
            prep_repo = InterviewPreparationRepository(session)
            step = await prep_repo.get_step_by_id(step_id)
            if not step:
                return {"status": "not_found"}

        ai_client = AIClient()
        system_prompt = build_preparation_test_system_prompt()
        prompt = build_preparation_test_prompt(
            step_title=step.title,
            step_content=step.content,
            deep_summary=step.deep_summary,
        )

        try:
            response_text = await ai_client.generate_text(
                prompt, system_prompt=system_prompt, max_tokens=2000
            )
            questions = _parse_test_questions(response_text)
            cb.record_success()
        except Exception as exc:
            cb.record_failure()
            logger.error("Test generation failed", step_id=step_id, error=str(exc))
            raise

        async with session_factory() as session:
            prep_repo = InterviewPreparationRepository(session)
            existing_test = await prep_repo.get_test_by_step(step_id)
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

        await _notify_user_test_ready(task, bot, chat_id, message_id, step_id, interview_id, locale)
        return {"status": "completed", "questions_count": len(questions)}

    except SoftTimeLimitExceeded:
        await task.handle_soft_timeout(bot, chat_id, message_id, locale)
        task.request.retries = task.max_retries
        raise

    except Exception as exc:
        logger.error("Test generation task failed", step_id=step_id, error=str(exc))
        if task.request.retries >= task.max_retries:
            await task.notify_user(bot, chat_id, message_id, get_text("prep-test-failed", locale))
        raise task.retry(exc=exc) from exc

    finally:
        await bot.session.close()


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="interviews.convert_deep_summary_to_docx",
    max_retries=1,
    default_retry_delay=10,
    soft_time_limit=60,
    time_limit=90,
)
def convert_deep_summary_to_docx_task(
    self,
    step_id: int,
    chat_id: int,
    locale: str = "ru",
    message_id: int | None = None,
) -> dict:
    return run_async(
        lambda sf: _convert_deep_summary_to_docx_async(
            self, sf, step_id, chat_id, locale, message_id
        )
    )


async def _convert_deep_summary_to_docx_async(
    task: HHBotTask,
    session_factory,
    step_id: int,
    chat_id: int,
    locale: str,
    message_id: int | None = None,
) -> dict:
    from aiogram.types import BufferedInputFile

    from src.core.i18n import get_text
    from src.repositories.interview import InterviewPreparationRepository
    from src.services.telegram.text_utils import BREAK_MARKER

    bot = task.create_bot()

    try:
        async with session_factory() as session:
            prep_repo = InterviewPreparationRepository(session)
            step = await prep_repo.get_step_by_id(step_id)
            if not step or not step.deep_summary:
                await task.notify_user(
                    bot, chat_id, message_id, get_text("prep-deep-not-ready", locale)
                )
                return {"status": "not_found"}

            header = f"# {get_text('prep-deep-title', locale)}: {step.title}\n\n"
            full_text = header + step.deep_summary.replace(BREAK_MARKER, "")
            safe_title = "".join(
                c if c.isalnum() or c in " -_" else "_" for c in step.title[:50]
            )
            filename = f"{safe_title}.docx"

        try:
            import contextlib
            import os
            import tempfile

            import pypandoc

            with tempfile.NamedTemporaryFile(
                suffix=".docx", delete=False
            ) as tmp:
                tmp_path = tmp.name
            try:
                pypandoc.convert_text(
                    full_text, "docx", format="md", outputfile=tmp_path
                )
                with open(tmp_path, "rb") as f:
                    docx_bytes = f.read()
            finally:
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)
        except Exception as exc:
            logger.error(
                "DOCX conversion failed",
                step_id=step_id,
                error=str(exc),
            )
            await task.notify_user(
                bot, chat_id, message_id, get_text("prep-docs-failed", locale)
            )
            return {"status": "conversion_failed"}

        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        from src.bot.modules.interviews.callbacks import InterviewCallback

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=get_text("btn-back", locale),
                        callback_data=InterviewCallback(
                            action="prep_step_deep",
                            interview_id=step.interview_id,
                            prep_step_id=step.id,
                        ).pack(),
                    )
                ]
            ]
        )
        doc = BufferedInputFile(docx_bytes, filename=filename)
        await bot.send_document(
            chat_id,
            doc,
            caption=get_text("prep-deep-title", locale),
            reply_markup=keyboard,
        )
        return {"status": "completed"}
    finally:
        await bot.session.close()


async def _notify_user_prep(
    task: HHBotTask,
    bot,
    chat_id: int,
    message_id: int,
    interview_id: int,
    locale: str,
) -> None:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.bot.modules.interviews.callbacks import InterviewCallback
    from src.core.i18n import get_text

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
    await task.notify_user(
        bot, chat_id, message_id, get_text("prep-guide-completed", locale), reply_markup=keyboard
    )


async def _notify_user_deep_summary(
    task: HHBotTask,
    bot,
    chat_id: int,
    message_id: int,
    step_id: int,
    interview_id: int,
    locale: str,
) -> None:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.bot.modules.interviews.callbacks import InterviewCallback
    from src.core.i18n import get_text

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
    await task.notify_user(
        bot, chat_id, message_id, get_text("prep-deep-completed", locale), reply_markup=keyboard
    )


async def _notify_user_test_ready(
    task: HHBotTask,
    bot,
    chat_id: int,
    message_id: int,
    step_id: int,
    interview_id: int,
    locale: str,
) -> None:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.bot.modules.interviews.callbacks import InterviewCallback
    from src.core.i18n import get_text

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
    await task.notify_user(
        bot, chat_id, message_id, get_text("prep-test-ready", locale), reply_markup=keyboard
    )
