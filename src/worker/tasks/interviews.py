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
    name="interviews.generate_employer_question_answer",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=240,
    time_limit=300,
)
def generate_employer_question_answer_task(
    self,
    interview_id: int,
    question_text: str,
    chat_id: int,
    message_id: int,
    locale: str,
    employer_qa_row_id: int | None = None,
) -> dict:
    return run_async(
        lambda sf: _generate_employer_question_answer_async(
            self,
            sf,
            interview_id,
            question_text,
            chat_id,
            message_id,
            locale,
            employer_qa_row_id=employer_qa_row_id,
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
    from src.services.ai.client import AIClient, close_ai_client
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
    ai_client: AIClient | None = None

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

        from src.bot.modules.interviews.keyboards import company_review_view_keyboard

        keyboard = company_review_view_keyboard(interview_id=interview_id, locale=locale)
        header = f"*{get_text('iv-company-review-title', locale)}*\n\n"

        try:
            from src.services.ai.streaming import stream_to_telegram

            accumulated = await stream_to_telegram(
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
            async with session_factory() as session:
                await InterviewRepository(session).update_company_review(
                    interview_id, accumulated
                )
                await session.commit()
            with contextlib.suppress(Exception):
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
            return {"status": "completed", "interview_id": interview_id}
        except Exception:
            try:
                review = await ai_client.generate_text(
                    prompt, system_prompt=system_prompt, max_tokens=2000
                )
                async with session_factory() as session:
                    await InterviewRepository(session).update_company_review(
                        interview_id, review
                    )
                    await session.commit()
                text = f"*{get_text('iv-company-review-title', locale)}*\n\n{review}"
                await task.notify_user(
                    bot,
                    chat_id,
                    message_id,
                    text,
                    reply_markup=keyboard,
                    parse_mode="Markdown",
                )
                cb.record_success()
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
        if ai_client is not None:
            await close_ai_client(ai_client)
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
    from src.services.ai.client import AIClient, close_ai_client
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
    ai_client: AIClient | None = None

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

        from src.bot.modules.interviews.keyboards import questions_to_ask_view_keyboard

        keyboard = questions_to_ask_view_keyboard(
            interview_id=interview_id, locale=locale
        )
        header = f"*{get_text('iv-questions-to-ask-title', locale)}*\n\n"

        try:
            from src.services.ai.streaming import stream_to_telegram

            accumulated = await stream_to_telegram(
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
            async with session_factory() as session:
                await InterviewRepository(session).update_questions_to_ask(
                    interview_id, accumulated
                )
                await session.commit()
            with contextlib.suppress(Exception):
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
            return {"status": "completed", "interview_id": interview_id}
        except Exception:
            try:
                questions = await ai_client.generate_text(
                    prompt, system_prompt=system_prompt, max_tokens=2000
                )
                async with session_factory() as session:
                    await InterviewRepository(session).update_questions_to_ask(
                        interview_id, questions
                    )
                    await session.commit()
                title = get_text("iv-questions-to-ask-title", locale)
                text = f"*{title}*\n\n{questions}"
                await task.notify_user(
                    bot,
                    chat_id,
                    message_id,
                    text,
                    reply_markup=keyboard,
                    parse_mode="Markdown",
                )
                cb.record_success()
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
        if ai_client is not None:
            await close_ai_client(ai_client)
        await bot.session.close()


_EMPLOYER_QUESTION_MAX_LEN = 4000


async def _generate_employer_question_answer_async(
    task: HHBotTask,
    session_factory: async_sessionmaker[AsyncSession],
    interview_id: int,
    question_text: str,
    chat_id: int,
    message_id: int,
    locale: str,
    employer_qa_row_id: int | None = None,
) -> dict:
    import secrets

    from celery.exceptions import SoftTimeLimitExceeded

    from src.bot.modules.autoparse import services as ap_service
    from src.bot.modules.interviews import services as interview_service
    from src.bot.modules.interviews.employer_qa_ui import build_employer_qa_item_full_html
    from src.bot.modules.interviews.keyboards import employer_qa_item_keyboard
    from src.core.constants import TELEGRAM_SAFE_LIMIT, AppSettingKey
    from src.core.i18n import get_text
    from src.repositories.interview import (
        InterviewEmployerQuestionRepository,
        InterviewRepository,
    )
    from src.repositories.work_experience import WorkExperienceRepository
    from src.services.ai.client import AIClient, close_ai_client
    from src.services.ai.prompts import (
        WorkExperienceEntry,
        truncate_employer_qa_thread,
    )

    regenerate = employer_qa_row_id is not None

    bot = task.create_bot()
    try:
        enabled = await task.check_enabled(
            AppSettingKey.TASK_EMPLOYER_QUESTION_ANSWER_ENABLED, session_factory
        )
        if not enabled:
            await task.notify_user(
                bot,
                chat_id,
                message_id,
                get_text("iv-employer-qa-disabled", locale),
            )
            return {"status": "disabled"}

        cb = await task.load_circuit_breaker(
            "employer_question_answer",
            AppSettingKey.CB_EMPLOYER_QUESTION_ANSWER_FAILURE_THRESHOLD,
            AppSettingKey.CB_EMPLOYER_QUESTION_ANSWER_RECOVERY_TIMEOUT,
            session_factory,
        )
        if not cb.is_call_allowed():
            await task.notify_user(
                bot,
                chat_id,
                message_id,
                get_text("iv-employer-qa-circuit", locale),
            )
            return {"status": "circuit_open"}

        try:
            async with session_factory() as session:
                interview = await InterviewRepository(session).get_with_relations(interview_id)
                if not interview or interview.is_deleted:
                    await task.notify_user(
                        bot,
                        chat_id,
                        message_id,
                        get_text("iv-not-found", locale),
                    )
                    return {"status": "not_found"}
                eq_repo = InterviewEmployerQuestionRepository(session)
                if regenerate:
                    row = await eq_repo.get_by_id_and_interview(employer_qa_row_id, interview_id)
                    if not row:
                        await task.notify_user(
                            bot,
                            chat_id,
                            message_id,
                            get_text("iv-not-found", locale),
                        )
                        return {"status": "not_found"}
                    q_trunc = (row.question_text or "").strip()[:_EMPLOYER_QUESTION_MAX_LEN]
                else:
                    q_trunc = (question_text or "").strip()[:_EMPLOYER_QUESTION_MAX_LEN]
                prior_rows = await eq_repo.list_by_interview_oldest_first(interview_id)
                if regenerate and employer_qa_row_id:
                    prior_rows = [r for r in prior_rows if r.id != employer_qa_row_id]
                previous_qa_raw = [
                    ((r.question_text or "").strip(), (r.answer_text or "").strip()) for r in prior_rows
                ]
                previous_qa, history_truncated = truncate_employer_qa_thread(previous_qa_raw)
                header_html = interview_service.format_vacancy_header(
                    interview.vacancy_title,
                    interview.company_name,
                    interview.experience_level,
                    interview.hh_vacancy_url,
                )
                user_id = interview.user_id
                we_rows = await WorkExperienceRepository(session).get_active_by_user(user_id)
                settings = await ap_service.get_user_autoparse_settings(session, user_id)
            about_me = (settings.get("about_me") or "").strip() or None

            experiences = [
                WorkExperienceEntry(
                    company_name=e.company_name,
                    stack=e.stack,
                    title=e.title,
                    period=e.period,
                    achievements=e.achievements,
                    duties=e.duties,
                )
                for e in we_rows
            ]

            variation_nonce = secrets.token_hex(12)
            ai = AIClient()
            try:
                answer = await ai.generate_employer_question_answer(
                    vacancy_title=interview.vacancy_title,
                    vacancy_description=interview.vacancy_description,
                    company_name=interview.company_name,
                    experience_level=interview.experience_level,
                    hh_vacancy_url=interview.hh_vacancy_url,
                    employer_question=q_trunc,
                    work_experiences=experiences,
                    about_me=about_me,
                    regenerate=regenerate,
                    variation_nonce=variation_nonce,
                    previous_qa=previous_qa or None,
                    history_truncated=history_truncated,
                )
            finally:
                await close_ai_client(ai)

            if not (answer or "").strip():
                cb.record_failure()
                await task.notify_user(
                    bot,
                    chat_id,
                    message_id,
                    get_text("iv-employer-qa-ai-empty", locale),
                )
                return {"status": "empty_answer"}

            async with session_factory() as session:
                repo = InterviewEmployerQuestionRepository(session)
                if regenerate:
                    row = await repo.get_by_id_and_interview(employer_qa_row_id, interview_id)
                    if not row:
                        await task.notify_user(
                            bot,
                            chat_id,
                            message_id,
                            get_text("iv-not-found", locale),
                        )
                        return {"status": "not_found"}
                    await repo.update(row, answer_text=answer.strip())
                    result_row_id = row.id
                else:
                    created = await repo.create_qa(
                        interview_id=interview_id,
                        question_text=q_trunc,
                        answer_text=answer.strip(),
                    )
                    result_row_id = created.id
                await session.commit()

            cb.record_success()

            from src.services.telegram.messenger import TelegramMessenger
            from src.services.telegram.text_utils import split_text_for_telegram

            title = get_text("iv-employer-qa-result-header", locale)
            q_label = get_text("iv-employer-qa-label-q", locale)
            a_label = get_text("iv-employer-qa-label-a", locale)
            full = build_employer_qa_item_full_html(
                header_html,
                result_header=title,
                q_label=q_label,
                a_label=a_label,
                question_text=q_trunc,
                answer_text=answer.strip(),
            )
            chunks = split_text_for_telegram(full, max_len=TELEGRAM_SAFE_LIMIT)
            if not chunks:
                chunks = [full]
            total_pages = len(chunks)
            messenger = TelegramMessenger(bot)
            await messenger.edit_or_send(
                chat_id,
                message_id,
                chunks[0],
                reply_markup=employer_qa_item_keyboard(
                    interview_id,
                    result_row_id,
                    locale=locale,
                    page=0,
                    total_pages=total_pages,
                ),
                parse_mode="HTML",
            )
            return {"status": "completed", "interview_id": interview_id}

        except SoftTimeLimitExceeded:
            await task.handle_soft_timeout(bot, chat_id, message_id, locale)
            task.request.retries = task.max_retries
            raise

        except Exception as exc:
            cb.record_failure()
            logger.error(
                "Employer question answer task failed",
                interview_id=interview_id,
                error=str(exc),
            )
            if task.request.retries >= task.max_retries:
                await task.notify_user(
                    bot,
                    chat_id,
                    message_id,
                    get_text("iv-employer-qa-failed", locale),
                )
            raise task.retry(exc=exc) from exc

    finally:
        await bot.session.close()
