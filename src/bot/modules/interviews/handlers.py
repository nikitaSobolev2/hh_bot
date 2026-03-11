"""Handlers for the My Interviews module.

Covers: paginated interview list, FSM creation flow (HH.ru + manual),
AI analysis, single interview detail, improvement detail, and status management.
"""

from __future__ import annotations

import httpx
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.modules.interviews import services as interview_service
from src.bot.modules.interviews.callbacks import InterviewCallback, InterviewFormCallback
from src.bot.modules.interviews.keyboards import (
    cancel_keyboard,
    confirm_keyboard,
    delete_confirm_keyboard,
    experience_level_keyboard,
    improvement_detail_keyboard,
    interview_detail_keyboard,
    interview_list_keyboard,
    questions_keyboard,
    skip_notes_keyboard,
    source_choice_keyboard,
)
from src.bot.modules.interviews.states import InterviewForm
from src.core.i18n import I18nContext
from src.models.interview import ImprovementStatus
from src.models.user import User
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

    await state.update_data(
        hh_vacancy_url=url,
        vacancy_title=data.get("title", ""),
        vacancy_description=data.get("description", ""),
        company_name=data.get("company_name", ""),
        experience_level=data.get("work_experience", ""),
    )

    parsed_info = _format_parsed_vacancy_preview(data)
    await wait_msg.edit_text(
        f"{i18n.get('iv-fsm-hh-parsed')}\n\n{parsed_info}\n\n{i18n.get('iv-fsm-now-add-questions')}",
        reply_markup=questions_keyboard(0, i18n),
        disable_web_page_preview=True,
    )
    await state.set_state(InterviewForm.adding_question)


def _format_parsed_vacancy_preview(data: dict) -> str:
    lines = []
    if data.get("title"):
        lines.append(f"<b>{data['title']}</b>")
    if data.get("company_name"):
        lines.append(f"Компания: {data['company_name']}")
    if data.get("work_experience"):
        lines.append(f"Опыт: {data['work_experience']}")
    return "\n".join(lines)


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
    i18n: I18nContext,
) -> None:
    await state.update_data(experience_level=callback_data.value)
    await state.set_state(InterviewForm.adding_question)
    await callback.message.edit_text(
        i18n.get("iv-fsm-now-add-questions"),
        reply_markup=questions_keyboard(0, i18n),
    )
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

    analyze_interview_task.delay(
        interview.id,
        callback.message.chat.id,
        callback.message.message_id,
        user.language_code or "ru",
        data.get("user_improvement_notes"),
    )

    await callback.answer()


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
        reply_markup=interview_detail_keyboard(interview.id, interview.improvements, i18n),
        disable_web_page_preview=True,
    )
    await callback.answer()


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

    generate_improvement_flow_task.delay(
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
