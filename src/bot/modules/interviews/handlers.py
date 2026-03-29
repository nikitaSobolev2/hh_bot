"""Handlers for the My Interviews module.

Covers: paginated interview list, FSM creation flow (HH.ru + manual),
AI analysis, single interview detail, improvement detail, and status management.
"""

from __future__ import annotations

import html
import httpx
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.modules.interviews import services as interview_service
from src.bot.modules.interviews.callbacks import InterviewCallback, InterviewFormCallback
from src.bot.modules.interviews.keyboards import (
    cancel_keyboard,
    company_review_view_keyboard,
    confirm_keyboard,
    delete_confirm_keyboard,
    employer_qa_cancel_keyboard,
    employer_qa_list_keyboard,
    experience_level_keyboard,
    improvement_detail_keyboard,
    interview_detail_keyboard,
    interview_list_keyboard,
    notes_stop_noting_reply_keyboard,
    notes_view_keyboard,
    prep_steps_keyboard,
    questions_keyboard,
    questions_to_ask_view_keyboard,
    skip_notes_keyboard,
    source_choice_keyboard,
)
from src.bot.modules.interviews.states import EmployerQuestionFlow, InterviewForm
from src.bot.utils.limits import get_max_message_length
from src.core.i18n import I18nContext
from src.models.interview import ImprovementStatus
from src.models.user import User
from src.repositories.interview import InterviewRepository
from src.services.parser.scraper import HHScraper

router = Router(name="interviews")

_scraper = HHScraper()


# ── List view ────────────────────────────────────────────────────────────────


async def show_interview_list(
    callback: CallbackQuery,
    user: User,
    i18n: I18nContext,
    session: AsyncSession | None = None,
    page: int = 0,
) -> None:
    if session is None:
        from src.db.engine import async_session_factory

        async with async_session_factory() as session:
            return await show_interview_list(callback, user, i18n, session, page)

    interviews, total = await interview_service.get_interviews_paginated(session, user.id, page)

    if not interviews and page == 0:
        await callback.message.edit_text(
            i18n.get("iv-list-empty"),
            reply_markup=interview_list_keyboard([], 0, 0, i18n),
        )
        return

    await callback.message.edit_text(
        i18n.get("iv-list-title"),
        reply_markup=interview_list_keyboard(list(interviews), page, total, i18n),
    )


@router.callback_query(InterviewCallback.filter(F.action == "list"))
async def handle_list(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await show_interview_list(callback, user, i18n, session, callback_data.page)
    await callback.answer()


# ── FSM: start new interview ─────────────────────────────────────────────────


@router.callback_query(InterviewCallback.filter(F.action == "new"))
async def fsm_start(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.clear()
    await state.set_state(InterviewForm.source_choice)
    await callback.message.edit_text(
        i18n.get("iv-fsm-source-choice"),
        reply_markup=source_choice_keyboard(i18n),
    )
    await callback.answer()


@router.callback_query(InterviewFormCallback.filter(F.action == "source"))
async def fsm_source_chosen(
    callback: CallbackQuery,
    callback_data: InterviewFormCallback,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    source = callback_data.value
    await state.update_data(source=source)

    if source == "hh":
        await state.set_state(InterviewForm.hh_link)
        await callback.message.edit_text(
            i18n.get("iv-fsm-enter-hh-link"),
            reply_markup=cancel_keyboard(i18n),
        )
    else:
        await state.set_state(InterviewForm.vacancy_title)
        await callback.message.edit_text(
            i18n.get("iv-fsm-enter-title"),
            reply_markup=cancel_keyboard(i18n),
        )
    await callback.answer()


# ── FSM: HH.ru branch ───────────────────────────────────────────────────────


@router.message(InterviewForm.hh_link)
async def fsm_hh_link_received(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    url = (message.text or "").strip()
    if not url.startswith("http"):
        await message.answer(
            i18n.get("iv-fsm-invalid-link"),
            reply_markup=cancel_keyboard(i18n),
        )
        return

    wait_msg = await message.answer(i18n.get("iv-fsm-parsing-hh"))

    try:
        async with httpx.AsyncClient() as client:
            data = await _scraper.parse_vacancy_page(client, url)
    except Exception:
        data = None

    if not data:
        await wait_msg.edit_text(
            i18n.get("iv-fsm-hh-parse-failed"),
            reply_markup=cancel_keyboard(i18n),
        )
        return

    data_dict = {
        "hh_vacancy_url": url,
        "vacancy_title": data.get("title", ""),
        "vacancy_description": data.get("description", ""),
        "company_name": data.get("company_name", ""),
        "experience_level": data.get("work_experience", ""),
    }
    await state.clear()
    await _save_and_show_interview(wait_msg, user, session, i18n, data_dict)


# ── FSM: manual branch ───────────────────────────────────────────────────────


@router.message(InterviewForm.vacancy_title)
async def fsm_vacancy_title_received(
    message: Message,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer(
            i18n.get("iv-fsm-title-empty"),
            reply_markup=cancel_keyboard(i18n),
        )
        return
    await state.update_data(vacancy_title=title)
    await state.set_state(InterviewForm.vacancy_description)
    await message.answer(
        i18n.get("iv-fsm-enter-description"),
        reply_markup=cancel_keyboard(i18n),
    )


@router.message(InterviewForm.vacancy_description)
async def fsm_vacancy_description_received(
    message: Message,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    description = (message.text or "").strip()
    await state.update_data(vacancy_description=description or None)
    await state.set_state(InterviewForm.company_name)
    await message.answer(
        i18n.get("iv-fsm-enter-company"),
        reply_markup=cancel_keyboard(i18n),
    )


@router.message(InterviewForm.company_name)
async def fsm_company_name_received(
    message: Message,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    company = (message.text or "").strip()
    await state.update_data(company_name=company or None)
    await state.set_state(InterviewForm.experience_level)
    await message.answer(
        i18n.get("iv-fsm-enter-experience"),
        reply_markup=experience_level_keyboard(i18n),
    )


@router.callback_query(InterviewFormCallback.filter(F.action == "exp"))
async def fsm_experience_chosen(
    callback: CallbackQuery,
    callback_data: InterviewFormCallback,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await state.update_data(experience_level=callback_data.value)
    data = await state.get_data()
    await state.clear()
    await _save_and_show_interview(callback.message, user, session, i18n, data)
    await callback.answer()


# ── FSM: Q&A collection ──────────────────────────────────────────────────────


@router.message(InterviewForm.adding_question)
async def fsm_question_received(
    message: Message,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    question = (message.text or "").strip()
    if not question:
        data = await state.get_data()
        qcount = len(data.get("questions", []))
        await message.answer(
            i18n.get("iv-fsm-question-empty"),
            reply_markup=questions_keyboard(qcount, i18n),
        )
        return
    await state.update_data(current_question=question)
    await state.set_state(InterviewForm.adding_answer)
    await message.answer(
        i18n.get("iv-fsm-enter-answer"),
        reply_markup=cancel_keyboard(i18n),
    )


@router.message(InterviewForm.adding_answer)
async def fsm_answer_received(
    message: Message,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    answer = (message.text or "").strip()
    data = await state.get_data()
    questions: list[dict[str, str]] = data.get("questions", [])
    questions.append({"question": data.get("current_question", ""), "answer": answer})
    await state.update_data(questions=questions, current_question=None)
    await state.set_state(InterviewForm.adding_question)
    await message.answer(
        i18n.get("iv-fsm-question-added", count=str(len(questions))),
        reply_markup=questions_keyboard(len(questions), i18n),
    )


@router.callback_query(InterviewFormCallback.filter(F.action == "questions_done"))
async def fsm_questions_done(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.set_state(InterviewForm.user_improvement_notes)
    await callback.message.edit_text(
        i18n.get("iv-fsm-enter-notes"),
        reply_markup=skip_notes_keyboard(i18n),
    )
    await callback.answer()


# ── FSM: improvement notes ───────────────────────────────────────────────────


@router.message(InterviewForm.user_improvement_notes)
async def fsm_notes_received(
    message: Message,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    notes = (message.text or "").strip()
    await state.update_data(user_improvement_notes=notes or None)
    await _show_confirm(message, state, i18n)


@router.callback_query(InterviewFormCallback.filter(F.action == "skip_notes"))
async def fsm_notes_skipped(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.update_data(user_improvement_notes=None)
    data = await state.get_data()
    await state.set_state(InterviewForm.confirm)
    await callback.message.edit_text(
        _build_confirm_text(data, i18n),
        reply_markup=confirm_keyboard(i18n),
    )
    await callback.answer()


async def _show_confirm(
    message: Message,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    await state.set_state(InterviewForm.confirm)
    await message.answer(
        _build_confirm_text(data, i18n),
        reply_markup=confirm_keyboard(i18n),
    )


def _build_confirm_text(data: dict, i18n: I18nContext) -> str:
    title = data.get("vacancy_title", "—")
    company = data.get("company_name") or "—"
    experience = data.get("experience_level") or "—"
    questions = data.get("questions", [])
    notes = data.get("user_improvement_notes") or i18n.get("iv-not-specified")

    q_lines = "\n".join(f"  {idx}. {qa['question']}" for idx, qa in enumerate(questions, 1))
    return (
        f"{i18n.get('iv-fsm-confirm-title')}\n\n"
        f"<b>{title}</b>\n"
        f"Компания: {company}\n"
        f"Опыт: {experience}\n"
        f"Вопросов: {len(questions)}\n\n"
        f"Вопросы:\n{q_lines}\n\n"
        f"Заметки: {notes}"
    )


# ── FSM: confirm → process ───────────────────────────────────────────────────


@router.callback_query(InterviewFormCallback.filter(F.action == "proceed"))
async def fsm_proceed(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    from src.worker.tasks.interviews import analyze_interview_task

    data = await state.get_data()
    await state.clear()
    await callback.answer()

    existing_interview_id: int | None = data.get("interview_id")

    if existing_interview_id:
        interview_repo = InterviewRepository(session)
        interview = await interview_repo.get_by_id(existing_interview_id)
    else:
        interview = await interview_service.create_interview(
            session=session,
            user_id=user.id,
            vacancy_title=data.get("vacancy_title", ""),
            vacancy_description=data.get("vacancy_description"),
            company_name=data.get("company_name"),
            experience_level=data.get("experience_level"),
            hh_vacancy_url=data.get("hh_vacancy_url"),
        )

    questions: list[dict[str, str]] = data.get("questions", [])
    await interview_service.bulk_create_questions(session, interview.id, questions)

    await callback.message.edit_text(i18n.get("iv-fsm-analyzing"))

    from src.core.celery_async import run_celery_task

    await run_celery_task(
        analyze_interview_task,
        interview.id,
        callback.message.chat.id,
        callback.message.message_id,
        user.language_code or "ru",
        data.get("user_improvement_notes"),
    )


# ── Cancel ───────────────────────────────────────────────────────────────────


@router.callback_query(InterviewCallback.filter(F.action == "cancel"))
async def handle_cancel_iv(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    i18n: I18nContext,
    session: AsyncSession,
) -> None:
    await state.clear()
    await show_interview_list(callback, user, i18n, session)
    await callback.answer()


@router.callback_query(InterviewFormCallback.filter(F.action == "cancel"))
async def handle_cancel_ivf(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    i18n: I18nContext,
    session: AsyncSession,
) -> None:
    await state.clear()
    await show_interview_list(callback, user, i18n, session)
    await callback.answer()


# ── Single interview detail ──────────────────────────────────────────────────


@router.callback_query(InterviewCallback.filter(F.action == "detail"))
async def handle_detail(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    interview = await interview_service.get_interview_detail(session, callback_data.interview_id)
    if not interview or interview.is_deleted:
        await callback.answer(i18n.get("iv-not-found"), show_alert=True)
        return

    header = interview_service.format_vacancy_header(
        interview.vacancy_title,
        interview.company_name,
        interview.experience_level,
        interview.hh_vacancy_url,
    )
    summary_text = interview.ai_summary or i18n.get("iv-no-summary")

    qa_lines = []
    for idx, qa in enumerate(interview.questions, 1):
        qa_lines.append(f"\n<b>Q{idx}:</b> {qa.question}")
        qa_lines.append(f"<b>A:</b> {qa.user_answer}")
    qa_section = "\n".join(qa_lines) if qa_lines else i18n.get("iv-no-questions")

    text = (
        f"{header}\n\n"
        f"<b>{i18n.get('iv-summary-label')}</b>\n{summary_text}\n\n"
        f"<b>{i18n.get('iv-qa-label')}</b>{qa_section}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=interview_detail_keyboard(
            interview.id,
            interview.improvements,
            i18n,
            has_questions=bool(interview.questions),
        ),
        disable_web_page_preview=True,
    )
    await callback.answer()


# ── Company review (AI) ─────────────────────────────────────────────────────


@router.callback_query(InterviewCallback.filter(F.action == "company_review"))
async def handle_company_review(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.repositories.interview import InterviewRepository

    interview = await InterviewRepository(session).get_with_relations(callback_data.interview_id)
    if not interview or interview.is_deleted:
        await callback.answer(i18n.get("iv-not-found"), show_alert=True)
        return

    header = interview_service.format_vacancy_header(
        interview.vacancy_title,
        interview.company_name,
        interview.experience_level,
        interview.hh_vacancy_url,
    )
    content = interview.company_review or i18n.get("iv-company-review-empty")
    text = f"{header}\n\n<b>{i18n.get('iv-company-review-title')}</b>\n\n{content}"

    await callback.message.edit_text(
        text,
        reply_markup=company_review_view_keyboard(
            callback_data.interview_id,
            i18n=i18n,
        ),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.callback_query(InterviewCallback.filter(F.action == "company_review_regenerate"))
async def handle_company_review_regenerate(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.core.celery_async import run_celery_task
    from src.repositories.interview import InterviewRepository
    from src.worker.tasks.interviews import generate_company_review_task

    interview = await InterviewRepository(session).get_with_relations(callback_data.interview_id)
    if not interview or interview.is_deleted:
        await callback.answer(i18n.get("iv-not-found"), show_alert=True)
        return

    wait_msg = await callback.message.edit_text(i18n.get("iv-generating-company-review"))
    await run_celery_task(
        generate_company_review_task,
        callback_data.interview_id,
        callback.message.chat.id,
        wait_msg.message_id if wait_msg else callback.message.message_id,
        user.language_code or "ru",
    )
    await callback.answer()


# ── Questions to ask (AI) ───────────────────────────────────────────────────


async def _show_questions_to_ask_view(
    message_or_callback,
    interview_id: int,
    session: AsyncSession,
    i18n: I18nContext,
    *,
    use_answer: bool = False,
    user: User | None = None,
    page: int = 0,
) -> None:
    """Show questions-to-ask view. Use use_answer=True when message is from user."""
    from src.repositories.interview import InterviewRepository
    from src.services.telegram.text_utils import split_text_for_telegram

    interview = await InterviewRepository(session).get_with_relations(interview_id)
    if not interview or interview.is_deleted:
        return
    header = interview_service.format_vacancy_header(
        interview.vacancy_title,
        interview.company_name,
        interview.experience_level,
        interview.hh_vacancy_url,
    )
    content = interview.questions_to_ask or i18n.get("iv-questions-to-ask-empty")
    max_len = get_max_message_length(user, "default") if user else 4000
    title_block = f"{header}\n\n<b>{i18n.get('iv-questions-to-ask-title')}</b>\n\n"
    full_text = title_block + content
    chunks = split_text_for_telegram(full_text, max_len=max_len)
    if not chunks:
        chunks = [title_block + content[:max_len - 20] + "\n..."]
    total_pages = len(chunks)
    page_index = max(0, min(page, total_pages - 1)) if total_pages else 0
    text = chunks[page_index] if chunks else title_block + i18n.get("iv-questions-to-ask-empty")
    kb = questions_to_ask_view_keyboard(
        interview_id, i18n=i18n, page=page_index, total_pages=total_pages
    )
    if use_answer or not hasattr(message_or_callback, "edit_text"):
        await message_or_callback.answer(
            text,
            parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
    else:
        await message_or_callback.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True,
        )


@router.callback_query(InterviewCallback.filter(F.action == "questions_to_ask"))
async def handle_questions_to_ask(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.repositories.interview import InterviewRepository

    interview = await InterviewRepository(session).get_with_relations(callback_data.interview_id)
    if not interview or interview.is_deleted:
        await callback.answer(i18n.get("iv-not-found"), show_alert=True)
        return

    await _show_questions_to_ask_view(
        callback.message,
        callback_data.interview_id,
        session,
        i18n,
        user=user,
        page=callback_data.page,
    )
    await callback.answer()


@router.callback_query(InterviewCallback.filter(F.action == "questions_to_ask_regenerate"))
async def handle_questions_to_ask_regenerate(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.core.celery_async import run_celery_task
    from src.repositories.interview import InterviewRepository
    from src.worker.tasks.interviews import generate_questions_to_ask_task

    interview = await InterviewRepository(session).get_with_relations(callback_data.interview_id)
    if not interview or interview.is_deleted:
        await callback.answer(i18n.get("iv-not-found"), show_alert=True)
        return

    wait_msg = await callback.message.edit_text(i18n.get("iv-generating-questions-to-ask"))
    await run_celery_task(
        generate_questions_to_ask_task,
        callback_data.interview_id,
        callback.message.chat.id,
        wait_msg.message_id if wait_msg else callback.message.message_id,
        user.language_code or "ru",
    )
    await callback.answer()


# ── Employer questions (AI answer + history) ────────────────────────────────


async def _show_employer_qa_list(
    message_or_callback,
    interview_id: int,
    session: AsyncSession,
    i18n: I18nContext,
    user: User,
    *,
    page: int = 0,
) -> None:
    """Render employer Q&A list with optional pagination over long text."""
    from src.repositories.interview import InterviewRepository
    from src.services.telegram.text_utils import split_text_for_telegram

    interview = await InterviewRepository(session).get_with_relations(interview_id)
    if not interview or interview.is_deleted:
        return
    if interview.user_id != user.id:
        return

    header = interview_service.format_vacancy_header(
        interview.vacancy_title,
        interview.company_name,
        interview.experience_level,
        interview.hh_vacancy_url,
    )
    rows = sorted(interview.employer_questions or [], key=lambda x: x.id, reverse=True)
    blocks: list[str] = []
    for idx, row in enumerate(rows, 1):
        blocks.append(
            f"<b>#{idx}</b>\n<b>{html.escape(i18n.get('iv-employer-qa-label-q'))}</b> "
            f"{html.escape(row.question_text)}\n\n"
            f"<b>{html.escape(i18n.get('iv-employer-qa-label-a'))}</b>\n{html.escape(row.answer_text)}"
        )
    body = "\n\n".join(blocks) if blocks else i18n.get("iv-employer-qa-empty")
    title_block = f"{header}\n\n<b>{i18n.get('iv-employer-qa-title')}</b>\n\n"
    full_text = title_block + body
    max_len = get_max_message_length(user, "default")
    chunks = split_text_for_telegram(full_text, max_len=max_len)
    if not chunks:
        chunks = [title_block + i18n.get("iv-employer-qa-empty")]
    total_pages = len(chunks)
    page_index = max(0, min(page, total_pages - 1)) if total_pages else 0
    text = chunks[page_index] if chunks else title_block + i18n.get("iv-employer-qa-empty")
    kb = employer_qa_list_keyboard(
        interview_id,
        i18n=i18n,
        page=page_index,
        total_pages=total_pages,
    )
    if not hasattr(message_or_callback, "edit_text"):
        await message_or_callback.answer(
            text,
            parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
    else:
        await message_or_callback.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True,
        )


@router.callback_query(InterviewCallback.filter(F.action == "employer_qa"))
async def handle_employer_qa_list(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.repositories.interview import InterviewRepository

    interview = await InterviewRepository(session).get_by_id(callback_data.interview_id)
    if not interview or interview.is_deleted:
        await callback.answer(i18n.get("iv-not-found"), show_alert=True)
        return
    if interview.user_id != user.id:
        await callback.answer(i18n.get("iv-not-found"), show_alert=True)
        return

    await _show_employer_qa_list(
        callback.message,
        callback_data.interview_id,
        session,
        i18n,
        user,
        page=callback_data.page,
    )
    await callback.answer()


@router.callback_query(InterviewCallback.filter(F.action == "employer_qa_regenerate"))
async def handle_employer_qa_regenerate(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.core.celery_async import run_celery_task
    from src.repositories.interview import (
        InterviewEmployerQuestionRepository,
        InterviewRepository,
    )
    from src.worker.tasks.interviews import generate_employer_question_answer_task

    qa_id = callback_data.employer_qa_id
    interview_id = callback_data.interview_id
    if not qa_id or not interview_id:
        await callback.answer(i18n.get("iv-not-found"), show_alert=True)
        return

    interview = await InterviewRepository(session).get_by_id(interview_id)
    if not interview or interview.is_deleted or interview.user_id != user.id:
        await callback.answer(i18n.get("iv-not-found"), show_alert=True)
        return

    row = await InterviewEmployerQuestionRepository(session).get_by_id_and_interview(
        qa_id, interview_id
    )
    if not row:
        await callback.answer(i18n.get("iv-not-found"), show_alert=True)
        return

    locale = user.language_code or "ru"
    await callback.message.edit_text(i18n.get("iv-employer-qa-generating"))
    await run_celery_task(
        generate_employer_question_answer_task,
        interview_id,
        "",
        callback.message.chat.id,
        callback.message.message_id,
        locale,
        employer_qa_row_id=qa_id,
    )
    await callback.answer()


@router.callback_query(InterviewCallback.filter(F.action == "employer_qa_new"))
async def handle_employer_qa_new(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.repositories.interview import InterviewRepository

    interview = await InterviewRepository(session).get_by_id(callback_data.interview_id)
    if not interview or interview.is_deleted:
        await callback.answer(i18n.get("iv-not-found"), show_alert=True)
        return
    if interview.user_id != user.id:
        await callback.answer(i18n.get("iv-not-found"), show_alert=True)
        return

    await state.set_state(EmployerQuestionFlow.awaiting_question)
    await state.update_data(employer_qa_interview_id=callback_data.interview_id)
    await callback.message.edit_text(
        i18n.get("iv-employer-qa-send-question"),
        reply_markup=employer_qa_cancel_keyboard(
            callback_data.interview_id,
            i18n=i18n,
        ),
    )
    await callback.answer()


@router.callback_query(InterviewCallback.filter(F.action == "employer_qa_cancel"))
async def handle_employer_qa_cancel(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.repositories.interview import InterviewRepository

    interview = await InterviewRepository(session).get_by_id(callback_data.interview_id)
    if not interview or interview.is_deleted or interview.user_id != user.id:
        await state.clear()
        await callback.answer(i18n.get("iv-not-found"), show_alert=True)
        return

    await state.clear()
    await _show_employer_qa_list(
        callback.message,
        callback_data.interview_id,
        session,
        i18n,
        user,
        page=0,
    )
    await callback.answer()


@router.message(EmployerQuestionFlow.awaiting_question, F.text)
async def handle_employer_qa_question_text(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.core.celery_async import run_celery_task
    from src.repositories.interview import InterviewRepository
    from src.worker.tasks.interviews import generate_employer_question_answer_task

    data = await state.get_data()
    interview_id = int(data.get("employer_qa_interview_id") or 0)
    if not interview_id:
        await state.clear()
        return

    interview = await InterviewRepository(session).get_by_id(interview_id)
    if not interview or interview.is_deleted or interview.user_id != user.id:
        await state.clear()
        await message.answer(i18n.get("iv-not-found"))
        return

    q = (message.text or "").strip()
    if len(q) < 3:
        await message.answer(i18n.get("iv-employer-qa-too-short"))
        return
    if len(q) > 4000:
        q = q[:4000]

    await state.clear()
    locale = user.language_code or "ru"
    wait_msg = await message.answer(i18n.get("iv-employer-qa-generating"))
    await run_celery_task(
        generate_employer_question_answer_task,
        interview_id,
        q,
        message.chat.id,
        wait_msg.message_id,
        locale,
    )


# ── Notes ────────────────────────────────────────────────────────────────────


def _paginate_notes(
    header: str,
    notes: list,
    i18n: I18nContext,
    max_len: int,
    full_content: bool,
) -> list[str]:
    """Split notes into pages that fit within max_len. Each page has header + notes section."""
    notes_title = f"\n\n<b>{i18n.get('iv-notes-title')}</b>\n\n"
    header_block = header + notes_title
    header_len = len(header_block)

    if not notes:
        return [header_block + i18n.get("iv-notes-empty")]

    pages: list[str] = []
    current_lines: list[str] = []
    current_len = header_len

    note_preview_len = 500
    for idx, note in enumerate(notes, 1):
        if full_content:
            content = note.content
        else:
            truncated = note.content[:note_preview_len]
            content = f"{truncated}{'...' if len(note.content) > note_preview_len else ''}"
        line = f"{idx}. {content}"
        max_note_len = max_len - header_len - 50
        if len(line) > max_note_len:
            line = line[: max_note_len - 3] + "..."
        line_len = len(line) + 1  # +1 for newline

        if current_len + line_len > max_len and current_lines:
            pages.append(header_block + "\n".join(current_lines))
            current_lines = []
            current_len = header_len

        current_lines.append(line)
        current_len += line_len

    if current_lines:
        pages.append(header_block + "\n".join(current_lines))

    return pages


def _build_notes_page(
    interview,
    notes: list,
    i18n: I18nContext,
    page: int,
    max_len: int,
    full_content: bool,
) -> tuple[str, int]:
    """Build a single page of notes. Returns (page_text, total_pages)."""
    header = interview_service.format_vacancy_header(
        interview.vacancy_title,
        interview.company_name,
        interview.experience_level,
        interview.hh_vacancy_url,
    )
    pages = _paginate_notes(header, notes, i18n, max_len, full_content)
    total_pages = len(pages)
    page_index = max(0, min(page, total_pages - 1)) if total_pages else 0
    text = pages[page_index] if pages else header + "\n\n" + i18n.get("iv-notes-empty")
    return text, total_pages


def _build_notes_view_text(interview, notes: list, i18n: I18nContext) -> str:
    """Legacy: single-page summary view (truncated notes). Used for noting flow."""
    header = interview_service.format_vacancy_header(
        interview.vacancy_title,
        interview.company_name,
        interview.experience_level,
        interview.hh_vacancy_url,
    )
    note_preview_len = 500
    if not notes:
        notes_section = i18n.get("iv-notes-empty")
    else:
        notes_section = "\n".join(
            f"{idx}. {note.content[:note_preview_len]}"
            f"{'...' if len(note.content) > note_preview_len else ''}"
            for idx, note in enumerate(notes, 1)
        )
    return f"{header}\n\n<b>{i18n.get('iv-notes-title')}</b>\n\n{notes_section}"


async def _show_notes_view(
    message_or_callback,
    interview_id: int,
    session: AsyncSession,
    i18n: I18nContext,
    user: User | None = None,
    *,
    page: int = 0,
    full_mode: bool = False,
    is_noting: bool = False,
    use_answer: bool = False,
) -> None:
    """Show notes view. Use use_answer=True when message is from user (not editable by bot)."""
    from src.repositories.interview import InterviewNoteRepository, InterviewRepository

    interview = await InterviewRepository(session).get_with_relations(interview_id)
    if not interview or interview.is_deleted:
        return
    notes = await InterviewNoteRepository(session).get_by_interview(interview_id)
    max_len = get_max_message_length(user, "default") if user else 4000

    if full_mode and notes:
        text, total_pages = _build_notes_page(
            interview, notes, i18n, page, max_len, full_content=True
        )
        kb = notes_view_keyboard(
            interview_id,
            i18n=i18n,
            is_noting=is_noting,
            page=page,
            total_pages=total_pages,
            full_mode=True,
        )
    else:
        text, total_pages = _build_notes_page(
            interview, notes, i18n, page, max_len, full_content=False
        )
        kb = notes_view_keyboard(
            interview_id,
            i18n=i18n,
            is_noting=is_noting,
            page=page,
            total_pages=total_pages,
            full_mode=False,
            notes_count=len(notes),
        )

    if use_answer or not hasattr(message_or_callback, "edit_text"):
        await message_or_callback.answer(
            text,
            parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
    else:
        await message_or_callback.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True,
        )


@router.callback_query(InterviewCallback.filter(F.action == "notes"))
async def handle_notes(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await _show_notes_view(
        callback.message,
        callback_data.interview_id,
        session,
        i18n,
        user=user,
        page=callback_data.page,
    )
    await callback.answer()


@router.callback_query(InterviewCallback.filter(F.action == "notes_full"))
async def handle_notes_full(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await _show_notes_view(
        callback.message,
        callback_data.interview_id,
        session,
        i18n,
        user=user,
        page=callback_data.page,
        full_mode=True,
    )
    await callback.answer()


async def _start_noting_flow(
    callback: CallbackQuery,
    interview_id: int,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
    return_to: str,
    user: User,
) -> None:
    """Shared logic for starting the noting flow from notes or questions view."""
    from src.repositories.interview import InterviewNoteRepository, InterviewRepository

    interview = await InterviewRepository(session).get_with_relations(interview_id)
    if not interview or interview.is_deleted:
        return
    await state.update_data(interview_id=interview_id, return_to=return_to)
    await state.set_state(InterviewForm.notes_noting)
    notes = await InterviewNoteRepository(session).get_by_interview(interview_id)
    max_len = get_max_message_length(user, "default")
    text, total_pages = _build_notes_page(
        interview, notes, i18n, 0, max_len, full_content=False
    )
    kb = notes_view_keyboard(
        interview_id,
        i18n=i18n,
        is_noting=True,
        page=0,
        total_pages=total_pages,
        full_mode=False,
        notes_count=len(notes),
    )
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=kb,
        disable_web_page_preview=True,
    )
    await callback.message.answer(
        i18n.get("iv-notes-noting-hint"),
        reply_markup=notes_stop_noting_reply_keyboard(i18n=i18n),
    )


@router.callback_query(InterviewCallback.filter(F.action == "notes_start"))
async def handle_notes_start(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.repositories.interview import InterviewRepository

    interview = await InterviewRepository(session).get_with_relations(callback_data.interview_id)
    if not interview or interview.is_deleted:
        await callback.answer(i18n.get("iv-not-found"), show_alert=True)
        return

    await _start_noting_flow(
        callback,
        callback_data.interview_id,
        state,
        session,
        i18n,
        return_to="notes",
        user=user,
    )
    await callback.answer()


@router.callback_query(
    InterviewCallback.filter(F.action == "notes_start_from_questions")
)
async def handle_notes_start_from_questions(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.repositories.interview import InterviewRepository

    interview = await InterviewRepository(session).get_with_relations(callback_data.interview_id)
    if not interview or interview.is_deleted:
        await callback.answer(i18n.get("iv-not-found"), show_alert=True)
        return

    await _start_noting_flow(
        callback,
        callback_data.interview_id,
        state,
        session,
        i18n,
        return_to="questions_to_ask",
        user=user,
    )
    await callback.answer()


@router.callback_query(InterviewCallback.filter(F.action == "notes_stop"))
async def handle_notes_stop(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from aiogram.types import ReplyKeyboardRemove

    data = await state.get_data()
    return_to = data.get("return_to", "notes")
    await state.clear()
    await callback.message.answer(
        i18n.get("iv-notes-stopped"),
        reply_markup=ReplyKeyboardRemove(),
    )
    if return_to == "questions_to_ask":
        await _show_questions_to_ask_view(
            callback.message,
            callback_data.interview_id,
            session,
            i18n,
            user=user,
        )
    else:
        await _show_notes_view(
            callback.message,
            callback_data.interview_id,
            session,
            i18n,
            user=user,
        )
    await callback.answer()


@router.callback_query(InterviewCallback.filter(F.action == "notes_edit"))
async def handle_notes_edit(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.repositories.interview import InterviewNoteRepository

    notes = await InterviewNoteRepository(session).get_by_interview(callback_data.interview_id)
    if not notes:
        await callback.answer(i18n.get("iv-notes-empty"), show_alert=True)
        return

    await state.update_data(interview_id=callback_data.interview_id)
    await state.set_state(InterviewForm.notes_edit_await_number)

    rows = [
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=InterviewCallback(
                    action="notes", interview_id=callback_data.interview_id
                ).pack(),
            )
        ]
    ]
    await callback.message.edit_text(
        i18n.get("iv-notes-enter-number-edit"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(InterviewCallback.filter(F.action == "notes_delete"))
async def handle_notes_delete(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.repositories.interview import InterviewNoteRepository

    notes = await InterviewNoteRepository(session).get_by_interview(callback_data.interview_id)
    if not notes:
        await callback.answer(i18n.get("iv-notes-empty"), show_alert=True)
        return

    await state.update_data(interview_id=callback_data.interview_id)
    await state.set_state(InterviewForm.notes_delete_await_number)

    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    rows = [
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=InterviewCallback(
                    action="notes", interview_id=callback_data.interview_id
                ).pack(),
            )
        ]
    ]
    await callback.message.edit_text(
        i18n.get("iv-notes-enter-number-delete"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.message(InterviewForm.notes_noting, Command("stop_notes"))
async def handle_stop_notes_command(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    """Alternative to ReplyKeyboard button: type /stop_notes to stop noting."""
    from aiogram.types import ReplyKeyboardRemove

    data = await state.get_data()
    interview_id = data.get("interview_id")
    return_to = data.get("return_to", "notes")
    await state.clear()
    await message.answer(
        i18n.get("iv-notes-stopped"),
        reply_markup=ReplyKeyboardRemove(),
    )
    if interview_id:
        if return_to == "questions_to_ask":
            await _show_questions_to_ask_view(
                message,
                interview_id,
                session,
                i18n,
                user=user,
                use_answer=True,
            )
        else:
            await _show_notes_view(
                message,
                interview_id,
                session,
                i18n,
                user=user,
                use_answer=True,
            )


@router.message(InterviewForm.notes_noting, F.text)
async def handle_notes_noting_message(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from aiogram.types import ReplyKeyboardRemove

    from src.repositories.interview import InterviewNoteRepository

    if message.text and message.text.strip() == i18n.get("btn-notes-stop"):
        data = await state.get_data()
        interview_id = data.get("interview_id")
        return_to = data.get("return_to", "notes")
        await state.clear()
        await message.answer(
            i18n.get("iv-notes-stopped"),
            reply_markup=ReplyKeyboardRemove(),
        )
        if interview_id:
            if return_to == "questions_to_ask":
                await _show_questions_to_ask_view(
                    message,
                    interview_id,
                    session,
                    i18n,
                    user=user,
                    use_answer=True,
                )
            else:
                await _show_notes_view(
                    message,
                    interview_id,
                    session,
                    i18n,
                    user=user,
                    use_answer=True,
                )
        return

    data = await state.get_data()
    interview_id = data.get("interview_id")
    if not interview_id:
        return

    notes = await InterviewNoteRepository(session).get_by_interview(interview_id)
    sort_order = max((n.sort_order for n in notes), default=-1) + 1
    await InterviewNoteRepository(session).create_note(
        interview_id=interview_id,
        content=(message.text or "").strip() or "(empty)",
        sort_order=sort_order,
    )
    await session.commit()
    await message.answer(i18n.get("iv-notes-added"))


@router.message(InterviewForm.notes_edit_await_number, F.text)
async def handle_notes_edit_number(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.repositories.interview import InterviewNoteRepository

    data = await state.get_data()
    interview_id = data.get("interview_id")
    if not interview_id:
        return

    notes = await InterviewNoteRepository(session).get_by_interview(interview_id)
    try:
        num = int((message.text or "").strip())
        if num < 1 or num > len(notes):
            raise ValueError("out of range")
    except (ValueError, TypeError):
        await message.answer(i18n.get("iv-notes-invalid-number"))
        return

    note = notes[num - 1]
    await state.update_data(note_to_edit_id=note.id, note_to_edit_num=num)
    await state.set_state(InterviewForm.notes_edit_await_text)

    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    rows = [
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=InterviewCallback(
                    action="notes", interview_id=interview_id
                ).pack(),
            )
        ]
    ]
    await message.answer(
        i18n.get("iv-notes-enter-new-content", n=str(num)),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.message(InterviewForm.notes_edit_await_text, F.text)
async def handle_notes_edit_text(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.repositories.interview import InterviewNoteRepository

    data = await state.get_data()
    interview_id = data.get("interview_id")
    note_id = data.get("note_to_edit_id")
    if not interview_id or not note_id:
        await state.clear()
        return

    await InterviewNoteRepository(session).update_content(
        note_id, (message.text or "").strip() or "(empty)"
    )
    await session.commit()
    await state.clear()

    await _show_notes_view(
        message,
        interview_id,
        session,
        i18n,
        user=user,
        use_answer=True,
    )
    await message.answer(i18n.get("iv-notes-updated"))


@router.message(InterviewForm.notes_delete_await_number, F.text)
async def handle_notes_delete_number(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.repositories.interview import InterviewNoteRepository

    data = await state.get_data()
    interview_id = data.get("interview_id")
    if not interview_id:
        return

    notes = await InterviewNoteRepository(session).get_by_interview(interview_id)
    try:
        num = int((message.text or "").strip())
        if num < 1 or num > len(notes):
            raise ValueError("out of range")
    except (ValueError, TypeError):
        await message.answer(i18n.get("iv-notes-invalid-number"))
        return

    note = notes[num - 1]
    await InterviewNoteRepository(session).delete_note(note.id)
    await session.commit()
    await state.clear()

    await _show_notes_view(
        message,
        interview_id,
        session,
        i18n,
        user=user,
        use_answer=True,
    )
    await message.answer(i18n.get("iv-notes-deleted"))


async def _save_and_show_interview(
    message_to_edit: Message,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
    data: dict,
) -> None:
    """Create interview from vacancy data and show interview detail view."""
    import contextlib

    from aiogram.exceptions import TelegramBadRequest

    interview = await interview_service.create_interview(
        session,
        user_id=user.id,
        vacancy_title=data.get("vacancy_title", ""),
        vacancy_description=data.get("vacancy_description"),
        company_name=data.get("company_name"),
        experience_level=data.get("experience_level"),
        hh_vacancy_url=data.get("hh_vacancy_url"),
    )
    header = interview_service.format_vacancy_header(
        interview.vacancy_title,
        interview.company_name,
        interview.experience_level,
        interview.hh_vacancy_url,
    )
    with contextlib.suppress(TelegramBadRequest):
        await message_to_edit.edit_text(
            f"{header}\n\n{i18n.get('iv-plain-created')}",
            reply_markup=interview_detail_keyboard(
                interview.id,
                [],
                i18n,
                has_questions=False,
            ),
            disable_web_page_preview=True,
        )


# ── Add results (for interview without Q&A) ─────────────────────────────────


@router.callback_query(InterviewCallback.filter(F.action == "add_results"))
async def handle_add_results(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.clear()
    await state.update_data(interview_id=callback_data.interview_id)
    await state.set_state(InterviewForm.adding_question)
    from src.bot.modules.interviews.keyboards import questions_keyboard

    await callback.message.edit_text(
        i18n.get("iv-fsm-now-add-questions"),
        reply_markup=questions_keyboard(0, i18n),
    )
    await callback.answer()


# ── Prepare me ───────────────────────────────────────────────────────────────


@router.callback_query(InterviewCallback.filter(F.action == "prepare_me"))
async def handle_prepare_me(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    import contextlib

    from aiogram.exceptions import TelegramBadRequest

    from src.core.celery_async import run_celery_task
    from src.repositories.interview import InterviewPreparationRepository
    from src.worker.tasks.interview_prep import generate_preparation_task

    prep_repo = InterviewPreparationRepository(session)
    steps = await prep_repo.get_steps_for_interview(callback_data.interview_id)
    if steps:
        text = f"<b>{i18n.get('prep-steps-title')}</b>\n\n{i18n.get('prep-steps-description')}"
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                text,
                reply_markup=prep_steps_keyboard(steps, callback_data.interview_id, i18n),
            )
        await callback.answer()
        return

    wait_msg = await callback.message.edit_text(i18n.get("prep-generating"))
    await run_celery_task(
        generate_preparation_task,
        callback_data.interview_id,
        callback.message.chat.id,
        wait_msg.message_id if wait_msg else callback.message.message_id,
        user.language_code or "ru",
    )
    await callback.answer()


# ── Preparation steps list ──────────────────────────────────────────────────


@router.callback_query(InterviewCallback.filter(F.action == "prep_steps"))
async def handle_prep_steps(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    import contextlib

    from aiogram.exceptions import TelegramBadRequest

    from src.repositories.interview import InterviewPreparationRepository

    prep_repo = InterviewPreparationRepository(session)
    steps = await prep_repo.get_steps_for_interview(callback_data.interview_id)

    text = f"<b>{i18n.get('prep-steps-title')}</b>\n\n{i18n.get('prep-steps-description')}"
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=prep_steps_keyboard(steps, callback_data.interview_id, i18n),
        )
    await callback.answer()


# ── Preparation step detail ─────────────────────────────────────────────────


@router.callback_query(InterviewCallback.filter(F.action == "prep_step_detail"))
async def handle_prep_step_detail(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    import contextlib

    from aiogram.exceptions import TelegramBadRequest

    from src.bot.modules.interviews.keyboards import prep_step_detail_keyboard
    from src.repositories.interview import InterviewPreparationRepository

    prep_repo = InterviewPreparationRepository(session)
    step = await prep_repo.get_step_by_id(callback_data.prep_step_id)
    if not step:
        await callback.answer(i18n.get("prep-step-not-found"), show_alert=True)
        return

    text = f"<b>{step.step_number}. {step.title}</b>\n\n{step.content}"
    max_len = get_max_message_length(user, "default")
    if len(text) > max_len:
        text = text[: max_len - 10] + "\n..."

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=prep_step_detail_keyboard(
                step.id,
                callback_data.interview_id,
                has_deep_summary=bool(step.deep_summary),
                has_test=bool(step.test),
                i18n=i18n,
            ),
        )
    await callback.answer()


# ── Skip preparation step ───────────────────────────────────────────────────


@router.callback_query(InterviewCallback.filter(F.action == "prep_skip"))
async def handle_prep_skip(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.models.interview import PrepStepStatus
    from src.repositories.interview import InterviewPreparationRepository

    prep_repo = InterviewPreparationRepository(session)
    await prep_repo.update_step_status(callback_data.prep_step_id, PrepStepStatus.SKIPPED)
    await session.commit()
    await handle_prep_steps(callback, callback_data, session, i18n)


# ── Continue (generate deep summary) ───────────────────────────────────────


@router.callback_query(InterviewCallback.filter(F.action == "prep_continue"))
async def handle_prep_continue(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    import contextlib

    from aiogram.exceptions import TelegramBadRequest

    from src.bot.modules.interviews.keyboards import deep_summary_keyboard
    from src.core.celery_async import run_celery_task
    from src.repositories.interview import InterviewPreparationRepository
    from src.services.telegram.text_utils import (
        parse_deep_learning_response,
        split_text_by_break,
        split_text_for_telegram,
    )
    from src.worker.tasks.interview_prep import generate_deep_summary_task

    prep_repo = InterviewPreparationRepository(session)
    step = await prep_repo.get_step_by_id(callback_data.prep_step_id)
    if step and step.deep_summary:
        summary, _ = parse_deep_learning_response(step.deep_summary)
        display_text = summary or step.deep_summary
        header = f"*{i18n.get('prep-deep-title')}: {step.title}*\n\n"
        full_text = header + display_text
        max_len = get_max_message_length(user, "default")
        chunks = split_text_by_break(full_text, max_len=max_len)
        if not chunks and full_text.strip():
            chunks = split_text_for_telegram(full_text, max_len=max_len)
        if chunks:
            keyboard = deep_summary_keyboard(
                step.id,
                callback_data.interview_id,
                has_test=bool(step.test),
                i18n=i18n,
            )
            bot = callback.message.bot
            chat_id = callback.message.chat.id
            with contextlib.suppress(TelegramBadRequest):
                if len(chunks) == 1:
                    await callback.message.edit_text(
                        chunks[0],
                        parse_mode="Markdown",
                        reply_markup=keyboard,
                    )
                else:
                    await callback.message.edit_text(
                        chunks[0],
                        parse_mode="Markdown",
                    )
                    for chunk in chunks[1:-1]:
                        await bot.send_message(
                            chat_id,
                            chunk,
                            parse_mode="Markdown",
                        )
                    await bot.send_message(
                        chat_id,
                        chunks[-1],
                        parse_mode="Markdown",
                        reply_markup=keyboard,
                    )
        await callback.answer()
        return

    wait_msg = await callback.message.edit_text(i18n.get("prep-generating-deep"))
    await run_celery_task(
        generate_deep_summary_task,
        callback_data.prep_step_id,
        callback_data.interview_id,
        callback.message.chat.id,
        wait_msg.message_id if wait_msg else callback.message.message_id,
        user.language_code or "ru",
    )
    await callback.answer()


# ── View deep summary ───────────────────────────────────────────────────────


@router.callback_query(InterviewCallback.filter(F.action == "prep_step_deep"))
async def handle_prep_step_deep(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    import contextlib

    from aiogram.exceptions import TelegramBadRequest

    from src.bot.modules.interviews.keyboards import deep_summary_keyboard
    from src.repositories.interview import InterviewPreparationRepository
    from src.services.telegram.text_utils import (
        parse_deep_learning_response,
        split_text_by_break,
        split_text_for_telegram,
    )

    prep_repo = InterviewPreparationRepository(session)
    step = await prep_repo.get_step_by_id(callback_data.prep_step_id)
    if not step or not step.deep_summary:
        await callback.answer(i18n.get("prep-deep-not-ready"), show_alert=True)
        return

    summary, _ = parse_deep_learning_response(step.deep_summary)
    display_text = summary or step.deep_summary
    header = f"*{i18n.get('prep-deep-title')}: {step.title}*\n\n"
    full_text = header + display_text
    max_len = get_max_message_length(user, "default")
    chunks = split_text_by_break(full_text, max_len=max_len)
    if not chunks and full_text.strip():
        chunks = split_text_for_telegram(full_text, max_len=max_len)

    if not chunks:
        await callback.answer()
        return

    keyboard = deep_summary_keyboard(
        step.id,
        callback_data.interview_id,
        has_test=bool(step.test),
        i18n=i18n,
    )
    bot = callback.message.bot
    chat_id = callback.message.chat.id
    is_document_message = callback.message.document is not None

    with contextlib.suppress(TelegramBadRequest):
        if is_document_message:
            await callback.message.delete()
            if len(chunks) == 1:
                await bot.send_message(
                    chat_id,
                    chunks[0],
                    parse_mode="Markdown",
                    reply_markup=keyboard,
                )
            else:
                for chunk in chunks[:-1]:
                    await bot.send_message(
                        chat_id,
                        chunk,
                        parse_mode="Markdown",
                    )
                await bot.send_message(
                    chat_id,
                    chunks[-1],
                    parse_mode="Markdown",
                    reply_markup=keyboard,
                )
        elif len(chunks) == 1:
            await callback.message.edit_text(
                chunks[0],
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
        else:
            await callback.message.edit_text(
                chunks[0],
                parse_mode="Markdown",
            )
            for chunk in chunks[1:-1]:
                await bot.send_message(
                    chat_id,
                    chunk,
                    parse_mode="Markdown",
                )
            await bot.send_message(
                chat_id,
                chunks[-1],
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
    await callback.answer()


# ── Download deep summary ──────────────────────────────────────────────────


@router.callback_query(InterviewCallback.filter(F.action == "prep_download"))
async def handle_prep_download(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    i18n: I18nContext,
) -> None:
    from src.bot.modules.interviews.keyboards import download_options_keyboard

    await callback.message.edit_text(
        i18n.get("prep-download-title"),
        reply_markup=download_options_keyboard(
            callback_data.prep_step_id,
            callback_data.interview_id,
            i18n=i18n,
        ),
    )
    await callback.answer()


@router.callback_query(InterviewCallback.filter(F.action == "prep_download_md"))
async def handle_prep_download_md(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup

    from src.repositories.interview import InterviewPreparationRepository
    from src.services.telegram.text_utils import parse_deep_learning_response

    prep_repo = InterviewPreparationRepository(session)
    step = await prep_repo.get_step_by_id(callback_data.prep_step_id)
    if not step or not step.deep_summary:
        await callback.answer(i18n.get("prep-deep-not-ready"), show_alert=True)
        return

    _, plan_content = parse_deep_learning_response(step.deep_summary)
    body = (plan_content or step.deep_summary).replace("\r\n", "\n")
    header = f"# {i18n.get('prep-deep-title')}: {step.title}\n\n"
    full_text = header + body
    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in step.title[:50])
    filename = f"{safe_title}.md"
    doc = BufferedInputFile(
        full_text.encode("utf-8"),
        filename=filename,
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=InterviewCallback(
                        action="prep_step_deep",
                        interview_id=step.interview_id,
                        prep_step_id=step.id,
                    ).pack(),
                )
            ]
        ]
    )
    await callback.message.bot.send_document(
        callback.message.chat.id,
        doc,
        caption=i18n.get("prep-deep-title"),
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(InterviewCallback.filter(F.action == "prep_download_docs"))
async def handle_prep_download_docs(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    user: User,
    i18n: I18nContext,
) -> None:
    from src.core.celery_async import run_celery_task
    from src.worker.tasks.interview_prep import convert_deep_summary_to_docx_task

    await callback.message.edit_text(i18n.get("prep-docs-generating"))
    await run_celery_task(
        convert_deep_summary_to_docx_task,
        callback_data.prep_step_id,
        callback.message.chat.id,
        user.language_code or "ru",
        callback.message.message_id,
    )
    await callback.answer()


@router.callback_query(InterviewCallback.filter(F.action == "prep_download_back"))
async def handle_prep_download_back(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    import contextlib

    from aiogram.exceptions import TelegramBadRequest

    from src.bot.modules.interviews.keyboards import deep_summary_keyboard
    from src.repositories.interview import InterviewPreparationRepository
    from src.services.telegram.text_utils import (
        parse_deep_learning_response,
        split_text_by_break,
        split_text_for_telegram,
    )

    prep_repo = InterviewPreparationRepository(session)
    step = await prep_repo.get_step_by_id(callback_data.prep_step_id)
    if not step or not step.deep_summary:
        await callback.answer(i18n.get("prep-deep-not-ready"), show_alert=True)
        return

    summary, _ = parse_deep_learning_response(step.deep_summary)
    display_text = summary or step.deep_summary
    header = f"*{i18n.get('prep-deep-title')}: {step.title}*\n\n"
    full_text = header + display_text
    max_len = get_max_message_length(user, "default")
    chunks = split_text_by_break(full_text, max_len=max_len)
    if not chunks:
        chunks = split_text_for_telegram(full_text, max_len=max_len)
    last_chunk = chunks[-1] if chunks else full_text
    keyboard = deep_summary_keyboard(
        callback_data.prep_step_id,
        callback_data.interview_id,
        has_test=bool(step.test),
        i18n=i18n,
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            last_chunk,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
    await callback.answer()


# ── Regenerate deep summary ──────────────────────────────────────────────────


@router.callback_query(InterviewCallback.filter(F.action == "prep_regenerate_deep"))
async def handle_prep_regenerate_deep(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.core.celery_async import run_celery_task
    from src.repositories.interview import InterviewPreparationRepository
    from src.worker.tasks.interview_prep import generate_deep_summary_task

    prep_repo = InterviewPreparationRepository(session)
    await prep_repo.update_step_deep_summary(callback_data.prep_step_id, None)
    await session.commit()

    wait_msg = await callback.message.edit_text(i18n.get("prep-generating-deep"))
    await run_celery_task(
        generate_deep_summary_task,
        callback_data.prep_step_id,
        callback_data.interview_id,
        callback.message.chat.id,
        wait_msg.message_id if wait_msg else callback.message.message_id,
        user.language_code or "ru",
    )
    await callback.answer()


# ── Regenerate whole plan ──────────────────────────────────────────────────


@router.callback_query(InterviewCallback.filter(F.action == "prep_regenerate_plan"))
async def handle_prep_regenerate_plan(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.core.celery_async import run_celery_task
    from src.repositories.interview import InterviewPreparationRepository
    from src.repositories.task import CeleryTaskRepository
    from src.worker.tasks.interview_prep import generate_preparation_task

    prep_repo = InterviewPreparationRepository(session)
    await prep_repo.delete_steps_for_interview(callback_data.interview_id)
    idempotency_key = f"interview_prep:{callback_data.interview_id}"
    await CeleryTaskRepository(session).delete_by_idempotency_key(idempotency_key)
    await session.commit()

    wait_msg = await callback.message.edit_text(i18n.get("prep-regenerating"))
    await run_celery_task(
        generate_preparation_task,
        callback_data.interview_id,
        callback.message.chat.id,
        wait_msg.message_id if wait_msg else callback.message.message_id,
        user.language_code or "ru",
    )
    await callback.answer()


# ── Create test ─────────────────────────────────────────────────────────────


@router.callback_query(InterviewCallback.filter(F.action == "prep_create_test"))
async def handle_prep_create_test(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    user: User,
    i18n: I18nContext,
) -> None:
    from src.core.celery_async import run_celery_task
    from src.worker.tasks.interview_prep import generate_test_task

    wait_msg = await callback.message.edit_text(i18n.get("prep-generating-test"))
    await run_celery_task(
        generate_test_task,
        callback_data.prep_step_id,
        callback_data.interview_id,
        callback.message.chat.id,
        wait_msg.message_id if wait_msg else callback.message.message_id,
        user.language_code or "ru",
    )
    await callback.answer()


@router.callback_query(InterviewCallback.filter(F.action == "prep_extend_test"))
async def handle_prep_extend_test(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    user: User,
    i18n: I18nContext,
) -> None:
    from src.core.celery_async import run_celery_task
    from src.worker.tasks.interview_prep import extend_prep_test_task

    wait_msg = await callback.message.edit_text(i18n.get("prep-extending-test"))
    await run_celery_task(
        extend_prep_test_task,
        callback_data.prep_step_id,
        callback_data.interview_id,
        callback.message.chat.id,
        wait_msg.message_id if wait_msg else callback.message.message_id,
        user.language_code or "ru",
    )
    await callback.answer()


# ── Test: show question ─────────────────────────────────────────────────────


def _build_test_question_text(
    question: dict,
    q_index: int,
    total: int,
    i18n: I18nContext,
    user_answers: dict | None = None,
) -> str:
    options_text = "\n".join(
        f"{chr(65 + i)}. {opt}" for i, opt in enumerate(question["options"])
    )
    text = (
        f"<b>{i18n.get('prep-test-question')} {q_index + 1}/{total}</b>\n\n"
        f"{question['question']}\n\n{options_text}"
    )
    answers = user_answers or {}
    if str(q_index) in answers:
        ans_idx = answers[str(q_index)]
        letter = chr(65 + ans_idx)
        text += f"\n\n{i18n.get('prep-test-your-answer')}: {letter}"
    return text


async def _show_test_question(
    callback: CallbackQuery,
    test,
    q_index: int,
    questions: list,
    i18n: I18nContext,
    step_id: int,
    interview_id: int,
) -> None:
    import contextlib

    from aiogram.exceptions import TelegramBadRequest

    from src.bot.modules.interviews.keyboards import test_question_keyboard

    question = questions[q_index]
    text = _build_test_question_text(
        question,
        q_index,
        len(questions),
        i18n,
        test.user_answers_json,
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=test_question_keyboard(
                question["options"],
                step_id,
                interview_id,
                q_index,
                total_questions=len(questions),
                i18n=i18n,
            ),
        )


@router.callback_query(InterviewCallback.filter(F.action == "prep_test_enter"))
async def handle_prep_test_enter(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.repositories.interview import InterviewPreparationRepository

    prep_repo = InterviewPreparationRepository(session)
    test = await prep_repo.get_test_by_step(callback_data.prep_step_id)
    if not test or not test.questions_json:
        await callback.answer(i18n.get("prep-test-not-ready"), show_alert=True)
        return

    questions = test.questions_json.get("questions", [])
    answers = dict(test.user_answers_json or {})
    first_unanswered = next(
        (i for i in range(len(questions)) if str(i) not in answers),
        len(questions),
    )
    if first_unanswered >= len(questions):
        correct_count = sum(
            1
            for idx, q in enumerate(questions)
            if str(idx) in answers and answers[str(idx)] == q["correct_index"]
        )
        score_text = f"{correct_count}/{len(questions)}"
        import contextlib

        from aiogram.exceptions import TelegramBadRequest

        from src.bot.modules.interviews.keyboards import test_results_keyboard

        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                f"<b>{i18n.get('prep-test-results')}: {score_text}</b>",
                parse_mode="HTML",
                reply_markup=test_results_keyboard(
                    callback_data.prep_step_id,
                    callback_data.interview_id,
                    i18n=i18n,
                ),
            )
    else:
        await _show_test_question(
            callback,
            test,
            first_unanswered,
            questions,
            i18n,
            callback_data.prep_step_id,
            callback_data.interview_id,
        )
    await callback.answer()


@router.callback_query(InterviewCallback.filter(F.action == "prep_test"))
async def handle_prep_test_start(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.repositories.interview import InterviewPreparationRepository

    prep_repo = InterviewPreparationRepository(session)
    test = await prep_repo.get_test_by_step(callback_data.prep_step_id)
    if not test or not test.questions_json:
        await callback.answer(i18n.get("prep-test-not-ready"), show_alert=True)
        return

    questions = test.questions_json.get("questions", [])
    q_index = callback_data.test_q_index
    if q_index >= len(questions):
        await callback.answer(i18n.get("prep-test-done"), show_alert=True)
        return

    await _show_test_question(
        callback,
        test,
        q_index,
        questions,
        i18n,
        callback_data.prep_step_id,
        callback_data.interview_id,
    )
    await callback.answer()


# ── Test: record answer ─────────────────────────────────────────────────────


@router.callback_query(InterviewCallback.filter(F.action == "prep_test_answer"))
async def handle_prep_test_answer(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await callback.answer()

    import contextlib

    from aiogram.exceptions import TelegramBadRequest

    from src.repositories.interview import InterviewPreparationRepository

    prep_repo = InterviewPreparationRepository(session)
    test = await prep_repo.get_test_by_step(callback_data.prep_step_id)
    if not test or not test.questions_json:
        return

    questions = test.questions_json.get("questions", [])
    q_index = callback_data.test_q_index
    user_answer = callback_data.test_answer

    answers = dict(test.user_answers_json or {})
    answers[str(q_index)] = user_answer
    await prep_repo.save_test_answers(callback_data.prep_step_id, answers)
    await session.commit()

    correct = questions[q_index]["correct_index"] if q_index < len(questions) else -1
    is_correct = user_answer == correct
    feedback = (
        i18n.get("prep-test-correct")
        if is_correct
        else (
            i18n.get("prep-test-wrong") + f" ({i18n.get('prep-test-right-answer')}: "
            f"{chr(65 + correct)}. {questions[q_index]['options'][correct]})"
        )
    )

    next_index = q_index + 1
    if next_index < len(questions):
        from src.bot.modules.interviews.keyboards import test_question_keyboard

        next_q = questions[next_index]
        next_text = _build_test_question_text(
            next_q,
            next_index,
            len(questions),
            i18n,
            answers,
        )
        text = f"{feedback}\n\n{next_text}"
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=test_question_keyboard(
                    next_q["options"],
                    callback_data.prep_step_id,
                    callback_data.interview_id,
                    next_index,
                    total_questions=len(questions),
                    i18n=i18n,
                ),
            )
    else:
        correct_count = sum(
            1
            for idx, q in enumerate(questions)
            if str(idx) in answers and answers[str(idx)] == q["correct_index"]
        )
        score_text = f"{correct_count}/{len(questions)}"
        from src.bot.modules.interviews.keyboards import test_results_keyboard

        results_kb = test_results_keyboard(
            callback_data.prep_step_id,
            callback_data.interview_id,
            i18n=i18n,
        )
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                f"{feedback}\n\n<b>{i18n.get('prep-test-results')}: {score_text}</b>",
                parse_mode="HTML",
                reply_markup=results_kb,
            )


def _make_back_to_step_keyboard(step_id: int, interview_id: int, i18n: I18nContext):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.bot.modules.interviews.callbacks import InterviewCallback

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=InterviewCallback(
                        action="prep_step_detail",
                        interview_id=interview_id,
                        prep_step_id=step_id,
                    ).pack(),
                )
            ]
        ]
    )


# ── Delete interview ─────────────────────────────────────────────────────────


@router.callback_query(InterviewCallback.filter(F.action == "delete"))
async def handle_delete(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    i18n: I18nContext,
) -> None:
    await callback.message.edit_text(
        i18n.get("iv-delete-confirm-prompt"),
        reply_markup=delete_confirm_keyboard(callback_data.interview_id, i18n),
    )
    await callback.answer()


@router.callback_query(InterviewCallback.filter(F.action == "delete_confirm"))
async def handle_delete_confirm(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    await interview_service.soft_delete_interview(session, callback_data.interview_id)
    await show_interview_list(callback, user, i18n, session)
    await callback.answer(i18n.get("iv-deleted"))


# ── Improvement detail ───────────────────────────────────────────────────────


@router.callback_query(InterviewCallback.filter(F.action == "improvement"))
async def handle_improvement_detail(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.repositories.interview import InterviewImprovementRepository, InterviewRepository

    improvement = await InterviewImprovementRepository(session).get_by_id(
        callback_data.improvement_id
    )
    if not improvement:
        await callback.answer(i18n.get("iv-not-found"), show_alert=True)
        return

    interview = await InterviewRepository(session).get_by_id(callback_data.interview_id)

    header = interview_service.format_vacancy_header(
        interview.vacancy_title if interview else "—",
        interview.company_name if interview else None,
        interview.experience_level if interview else None,
        interview.hh_vacancy_url if interview else None,
    )

    flow_label = i18n.get("iv-improvement-flow-label")
    flow_section = ""
    if improvement.improvement_flow:
        flow_section = f"\n\n<b>{flow_label}</b>\n{improvement.improvement_flow}"

    text = (
        f"{header}\n\n<b>{improvement.technology_title}</b>\n\n{improvement.summary}{flow_section}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=improvement_detail_keyboard(
            callback_data.interview_id,
            callback_data.improvement_id,
            has_flow=bool(improvement.improvement_flow),
            i18n=i18n,
        ),
        disable_web_page_preview=True,
    )
    await callback.answer()


# ── Generate improvement flow ────────────────────────────────────────────────


@router.callback_query(InterviewCallback.filter(F.action == "gen_flow"))
async def handle_generate_flow(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    from src.repositories.interview import InterviewRepository
    from src.worker.tasks.interviews import generate_improvement_flow_task

    interview = await InterviewRepository(session).get_by_id(callback_data.interview_id)
    if not interview:
        await callback.answer(i18n.get("iv-not-found"), show_alert=True)
        return

    await callback.message.edit_text(i18n.get("iv-generating-flow"))
    await callback.answer()

    from src.core.celery_async import run_celery_task

    await run_celery_task(
        generate_improvement_flow_task,
        callback_data.improvement_id,
        callback_data.interview_id,
        callback.message.chat.id,
        callback.message.message_id,
        user.language_code or "ru",
    )


# ── Set improvement status ───────────────────────────────────────────────────


@router.callback_query(InterviewCallback.filter(F.action.in_({"set_success", "set_error"})))
async def handle_set_status(
    callback: CallbackQuery,
    callback_data: InterviewCallback,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    status = (
        ImprovementStatus.SUCCESS
        if callback_data.action == "set_success"
        else ImprovementStatus.ERROR
    )
    await interview_service.update_improvement_status(session, callback_data.improvement_id, status)

    from src.repositories.interview import InterviewImprovementRepository, InterviewRepository

    improvement = await InterviewImprovementRepository(session).get_by_id(
        callback_data.improvement_id
    )
    interview = await InterviewRepository(session).get_by_id(callback_data.interview_id)

    if not improvement or not interview:
        await callback.answer()
        return

    header = interview_service.format_vacancy_header(
        interview.vacancy_title,
        interview.company_name,
        interview.experience_level,
        interview.hh_vacancy_url,
    )

    flow_label = i18n.get("iv-improvement-flow-label")
    flow_section = ""
    if improvement.improvement_flow:
        flow_section = f"\n\n<b>{flow_label}</b>\n{improvement.improvement_flow}"

    text = (
        f"{header}\n\n<b>{improvement.technology_title}</b>\n\n{improvement.summary}{flow_section}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=improvement_detail_keyboard(
            callback_data.interview_id,
            callback_data.improvement_id,
            has_flow=bool(improvement.improvement_flow),
            i18n=i18n,
        ),
        disable_web_page_preview=True,
    )
    await callback.answer()
