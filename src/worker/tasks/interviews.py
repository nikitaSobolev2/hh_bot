"""Celery tasks for interview analysis and improvement flow generation."""

from __future__ import annotations

import contextlib

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.logging import get_logger
from src.worker.app import celery_app
from src.worker.base_task import HHBotTask
from src.worker.utils import run_async

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="interviews.analyze",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=240,
    time_limit=300,
)
def analyze_interview_task(
    self,
    interview_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
    user_improvement_notes: str | None = None,
) -> dict:
    return run_async(
        lambda sf: _analyze_interview_async(
            self,
            sf,
            interview_id,
            chat_id,
            message_id,
            locale,
            user_improvement_notes,
        )
    )


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="interviews.generate_company_review",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=120,
    time_limit=180,
)
def generate_company_review_task(
    self,
    interview_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
) -> dict:
    return run_async(
        lambda sf: _generate_company_review_async(
            self, sf, interview_id, chat_id, message_id, locale
        )
    )


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="interviews.generate_questions_to_ask",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=120,
    time_limit=180,
)
def generate_questions_to_ask_task(
    self,
    interview_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
) -> dict:
    return run_async(
        lambda sf: _generate_questions_to_ask_async(
            self, sf, interview_id, chat_id, message_id, locale
        )
    )


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="interviews.generate_flow",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=240,
    time_limit=300,
)
def generate_improvement_flow_task(
    self,
    improvement_id: int,
    interview_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
) -> dict:
    return run_async(
        lambda sf: _generate_flow_async(
            self,
            sf,
            improvement_id,
            interview_id,
            chat_id,
            message_id,
            locale,
        )
    )


async def _analyze_interview_async(
    task: HHBotTask,
    session_factory: async_sessionmaker[AsyncSession],
    interview_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
    user_improvement_notes: str | None,
) -> dict:
    from celery.exceptions import SoftTimeLimitExceeded

    from src.core.constants import AppSettingKey
    from src.core.i18n import get_text

    enabled = await task.check_enabled(
        AppSettingKey.TASK_INTERVIEW_ANALYSIS_ENABLED, session_factory
    )
    if not enabled:
        return {"status": "disabled"}

    cb = await task.load_circuit_breaker(
        "interview_analysis",
        AppSettingKey.CB_INTERVIEW_ANALYSIS_FAILURE_THRESHOLD,
        AppSettingKey.CB_INTERVIEW_ANALYSIS_RECOVERY_TIMEOUT,
        session_factory,
    )
    if not cb.is_call_allowed():
        return {"status": "circuit_open"}

    bot = task.create_bot()
    idempotency_key = f"analyze_interview:{interview_id}"

    if await task.is_already_completed(idempotency_key, session_factory):
        return {"status": "already_completed"}

    try:
        async with session_factory() as session:
            from src.repositories.interview import InterviewRepository

            interview = await InterviewRepository(session).get_with_relations(interview_id)
            if not interview:
                return {"status": "error", "message": "Interview not found"}

            if interview.ai_summary is not None:
                return {"status": "already_completed"}

            questions = [
                {"question": q.question, "answer": q.user_answer} for q in interview.questions
            ]

        async with session_factory() as session:
            from src.bot.modules.interviews.services import analyze_and_save

            summary, improvements = await analyze_and_save(
                session=session,
                interview_id=interview_id,
                vacancy_title=interview.vacancy_title,
                vacancy_description=interview.vacancy_description,
                company_name=interview.company_name,
                experience_level=interview.experience_level,
                questions_answers=questions,
                user_improvement_notes=user_improvement_notes,
            )

        from src.bot.modules.interviews.keyboards import interview_detail_keyboard
        from src.bot.modules.interviews.services import format_vacancy_header

        header = format_vacancy_header(
            interview.vacancy_title,
            interview.company_name,
            interview.experience_level,
            interview.hh_vacancy_url,
        )
        summary_text = summary or get_text("iv-no-summary", locale)
        text = f"{header}\n\n<b>{get_text('iv-summary-label', locale)}</b>\n{summary_text}"

        await task.notify_user(
            bot,
            chat_id,
            message_id,
            text,
            reply_markup=interview_detail_keyboard(
                interview_id=interview_id,
                improvements=improvements,
                locale=locale,
            ),
        )

        cb.record_success()
        await task.mark_completed(
            idempotency_key, "interview_analysis", interview_id, session_factory
        )
        return {"status": "completed", "interview_id": interview_id}

    except SoftTimeLimitExceeded:
        await task.handle_soft_timeout(bot, chat_id, message_id, locale)
        task.request.retries = task.max_retries
        raise

    except Exception as exc:
        cb.record_failure()
        logger.error("Interview analysis task failed", interview_id=interview_id, error=str(exc))

        if task.request.retries >= task.max_retries:
            await task.notify_user(bot, chat_id, message_id, get_text("iv-analysis-failed", locale))

        raise task.retry(exc=exc) from exc

    finally:
        await bot.session.close()


async def _generate_flow_async(
    task: HHBotTask,
    session_factory: async_sessionmaker[AsyncSession],
    improvement_id: int,
    interview_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
) -> dict:
    from celery.exceptions import SoftTimeLimitExceeded

    from src.core.constants import AppSettingKey
    from src.core.i18n import get_text

    enabled = await task.check_enabled(AppSettingKey.TASK_IMPROVEMENT_FLOW_ENABLED, session_factory)
    if not enabled:
        return {"status": "disabled"}

    cb = await task.load_circuit_breaker(
        "improvement_flow",
        AppSettingKey.CB_IMPROVEMENT_FLOW_FAILURE_THRESHOLD,
        AppSettingKey.CB_IMPROVEMENT_FLOW_RECOVERY_TIMEOUT,
        session_factory,
    )
    if not cb.is_call_allowed():
        return {"status": "circuit_open"}

    bot = task.create_bot()
    idempotency_key = f"generate_flow:{improvement_id}"

    if await task.is_already_completed(idempotency_key, session_factory):
        return {"status": "already_completed"}

    try:
        async with session_factory() as session:
            from src.repositories.interview import (
                InterviewImprovementRepository,
                InterviewRepository,
            )

            improvement = await InterviewImprovementRepository(session).get_by_id(improvement_id)
            if not improvement:
                return {"status": "error", "message": "Improvement not found"}

            if improvement.improvement_flow is not None:
                return {"status": "already_completed"}

            interview = await InterviewRepository(session).get_by_id(interview_id)

        async with session_factory() as session:
            from src.bot.modules.interviews.services import generate_and_save_improvement_flow

            flow = await generate_and_save_improvement_flow(
                session=session,
                improvement_id=improvement_id,
                vacancy_title=interview.vacancy_title if interview else "",
                vacancy_description=interview.vacancy_description if interview else None,
            )

        async with session_factory() as session:
            from src.repositories.interview import InterviewImprovementRepository

            improvement = await InterviewImprovementRepository(session).get_by_id(improvement_id)

        from src.bot.modules.interviews.keyboards import improvement_detail_keyboard
        from src.bot.modules.interviews.services import format_vacancy_header

        header = format_vacancy_header(
            interview.vacancy_title if interview else "—",
            interview.company_name if interview else None,
            interview.experience_level if interview else None,
            interview.hh_vacancy_url if interview else None,
        )

        flow_label = get_text("iv-improvement-flow-label", locale)
        flow_section = (
            f"\n\n<b>{flow_label}</b>\n{flow}"
            if flow
            else f"\n\n{get_text('iv-flow-generation-failed', locale)}"
        )

        tech_title = improvement.technology_title if improvement else "—"
        imp_summary = improvement.summary if improvement else ""
        text = f"{header}\n\n<b>{tech_title}</b>\n\n{imp_summary}{flow_section}"

        await task.notify_user(
            bot,
            chat_id,
            message_id,
            text,
            reply_markup=improvement_detail_keyboard(
                interview_id=interview_id,
                improvement_id=improvement_id,
                has_flow=bool(flow),
                locale=locale,
            ),
        )

        cb.record_success()
        await task.mark_completed(
            idempotency_key, "improvement_flow", improvement_id, session_factory
        )
        return {"status": "completed", "improvement_id": improvement_id}

    except SoftTimeLimitExceeded:
        await task.handle_soft_timeout(bot, chat_id, message_id, locale)
        task.request.retries = task.max_retries
        raise

    except Exception as exc:
        cb.record_failure()
        logger.error("Improvement flow task failed", improvement_id=improvement_id, error=str(exc))

        if task.request.retries >= task.max_retries:
            await task.notify_user(
                bot, chat_id, message_id, get_text("iv-flow-generation-failed", locale)
            )

        raise task.retry(exc=exc) from exc

    finally:
        await bot.session.close()


async def _generate_company_review_async(
    task: HHBotTask,
    session_factory: async_sessionmaker[AsyncSession],
    interview_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
) -> dict:
    from celery.exceptions import SoftTimeLimitExceeded

    from src.core.constants import AppSettingKey
    from src.core.i18n import get_text
    from src.repositories.interview import InterviewRepository
    from src.services.ai.client import AIClient
    from src.services.ai.prompts import (
        build_company_review_prompt,
        build_company_review_system_prompt,
    )

    enabled = await task.check_enabled(
        AppSettingKey.TASK_COMPANY_REVIEW_ENABLED, session_factory
    )
    if not enabled:
        return {"status": "disabled"}

    cb = await task.load_circuit_breaker(
        "company_review",
        AppSettingKey.CB_COMPANY_REVIEW_FAILURE_THRESHOLD,
        AppSettingKey.CB_COMPANY_REVIEW_RECOVERY_TIMEOUT,
        session_factory,
    )
    if not cb.is_call_allowed():
        return {"status": "circuit_open"}

    bot = task.create_bot()

    try:
        async with session_factory() as session:
            interview = await InterviewRepository(session).get_with_relations(interview_id)
            if not interview:
                return {"status": "not_found"}

        prompt = build_company_review_prompt(
            vacancy_title=interview.vacancy_title,
            vacancy_description=interview.vacancy_description,
            company_name=interview.company_name,
            experience_level=interview.experience_level,
        )
        system_prompt = build_company_review_system_prompt()
        ai_client = AIClient()

        from src.bot.modules.interviews.keyboards import interview_detail_keyboard

        keyboard = interview_detail_keyboard(
            interview_id=interview_id,
            improvements=interview.improvements,
            locale=locale,
            has_questions=bool(interview.questions),
        )
        header = get_text("iv-company-review-title", locale) + "\n\n"

        try:
            from src.services.ai.streaming import stream_to_telegram

            await stream_to_telegram(
                bot=bot,
                chat_id=chat_id,
                token_stream=ai_client.stream_text(
                    prompt,
                    system_prompt=system_prompt,
                    max_tokens=2000,
                ),
                initial_text=header,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
            cb.record_success()
            with contextlib.suppress(Exception):
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
            return {"status": "completed", "interview_id": interview_id}
        except Exception:
            try:
                review = await ai_client.generate_text(
                    prompt, system_prompt=system_prompt, max_tokens=2000
                )
                cb.record_success()
                text = f"*{get_text('iv-company-review-title', locale)}*\n\n{review}"
                await task.notify_user(
                    bot,
                    chat_id,
                    message_id,
                    text,
                    reply_markup=keyboard,
                    parse_mode="Markdown",
                )
                return {"status": "completed", "interview_id": interview_id}
            except Exception as exc:
                cb.record_failure()
                logger.error(
                    "Company review generation failed",
                    interview_id=interview_id,
                    error=str(exc),
                )
                raise

    except SoftTimeLimitExceeded:
        await task.handle_soft_timeout(bot, chat_id, message_id, locale)
        task.request.retries = task.max_retries
        raise

    except Exception as exc:
        logger.error(
            "Company review task failed", interview_id=interview_id, error=str(exc)
        )
        if task.request.retries >= task.max_retries:
            await task.notify_user(
                bot, chat_id, message_id, get_text("iv-company-review-failed", locale)
            )
        raise task.retry(exc=exc) from exc

    finally:
        await bot.session.close()


async def _generate_questions_to_ask_async(
    task: HHBotTask,
    session_factory: async_sessionmaker[AsyncSession],
    interview_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
) -> dict:
    from celery.exceptions import SoftTimeLimitExceeded

    from src.core.constants import AppSettingKey
    from src.core.i18n import get_text
    from src.repositories.interview import InterviewRepository
    from src.services.ai.client import AIClient
    from src.services.ai.prompts import (
        build_questions_to_ask_prompt,
        build_questions_to_ask_system_prompt,
    )

    enabled = await task.check_enabled(
        AppSettingKey.TASK_QUESTIONS_TO_ASK_ENABLED, session_factory
    )
    if not enabled:
        return {"status": "disabled"}

    cb = await task.load_circuit_breaker(
        "questions_to_ask",
        AppSettingKey.CB_QUESTIONS_TO_ASK_FAILURE_THRESHOLD,
        AppSettingKey.CB_QUESTIONS_TO_ASK_RECOVERY_TIMEOUT,
        session_factory,
    )
    if not cb.is_call_allowed():
        return {"status": "circuit_open"}

    bot = task.create_bot()

    try:
        async with session_factory() as session:
            interview = await InterviewRepository(session).get_with_relations(interview_id)
            if not interview:
                return {"status": "not_found"}

        prompt = build_questions_to_ask_prompt(
            vacancy_title=interview.vacancy_title,
            vacancy_description=interview.vacancy_description,
            company_name=interview.company_name,
            experience_level=interview.experience_level,
        )
        system_prompt = build_questions_to_ask_system_prompt()
        ai_client = AIClient()

        from src.bot.modules.interviews.keyboards import interview_detail_keyboard

        keyboard = interview_detail_keyboard(
            interview_id=interview_id,
            improvements=interview.improvements,
            locale=locale,
            has_questions=bool(interview.questions),
        )
        header = get_text("iv-questions-to-ask-title", locale) + "\n\n"

        try:
            from src.services.ai.streaming import stream_to_telegram

            await stream_to_telegram(
                bot=bot,
                chat_id=chat_id,
                token_stream=ai_client.stream_text(
                    prompt,
                    system_prompt=system_prompt,
                    max_tokens=2000,
                ),
                initial_text=header,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
            cb.record_success()
            with contextlib.suppress(Exception):
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
            return {"status": "completed", "interview_id": interview_id}
        except Exception:
            try:
                questions = await ai_client.generate_text(
                    prompt, system_prompt=system_prompt, max_tokens=2000
                )
                cb.record_success()
                text = f"*{get_text('iv-questions-to-ask-title', locale)}*\n\n{questions}"
                await task.notify_user(
                    bot,
                    chat_id,
                    message_id,
                    text,
                    reply_markup=keyboard,
                    parse_mode="Markdown",
                )
                return {"status": "completed", "interview_id": interview_id}
            except Exception as exc:
                cb.record_failure()
                logger.error(
                    "Questions to ask generation failed",
                    interview_id=interview_id,
                    error=str(exc),
                )
                raise

    except SoftTimeLimitExceeded:
        await task.handle_soft_timeout(bot, chat_id, message_id, locale)
        task.request.retries = task.max_retries
        raise

    except Exception as exc:
        logger.error(
            "Questions to ask task failed", interview_id=interview_id, error=str(exc)
        )
        if task.request.retries >= task.max_retries:
            await task.notify_user(
                bot,
                chat_id,
                message_id,
                get_text("iv-questions-to-ask-failed", locale),
            )
        raise task.retry(exc=exc) from exc

    finally:
        await bot.session.close()
