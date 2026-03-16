"""Handlers for the Standard Interview Q&A module."""

from __future__ import annotations

import contextlib

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.modules.interview_qa.callbacks import InterviewQACallback
from src.bot.modules.interview_qa.keyboards import (
    answer_back_keyboard,
    generate_select_keyboard,
    interview_add_select_keyboard,
    interview_qa_list_keyboard,
    question_detail_keyboard,
    why_new_job_reasons_keyboard,
)
from src.bot.modules.interview_qa.states import InterviewQAForm
from src.core.i18n import I18nContext
from src.models.user import User
from src.repositories.interview_qa import StandardQuestionRepository
from src.repositories.work_experience import WorkExperienceRepository

router = Router(name="interview_qa")

_WHY_REASON_ANSWERS = {
    "salary": "iqa-why-answer-salary",
    "bored": "iqa-why-answer-bored",
    "relationship": "iqa-why-answer-relationship",
    "growth": "iqa-why-answer-growth",
    "relocation": "iqa-why-answer-relocation",
    "other": "iqa-why-answer-other",
}


async def show_interview_qa_list(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    repo = StandardQuestionRepository(session)
    questions = await repo.get_ai_generated(user.id)

    text = f"<b>{i18n.get('iqa-list-title')}</b>\n\n{i18n.get('iqa-list-description')}"
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=interview_qa_list_keyboard(questions, i18n),
        )


@router.callback_query(InterviewQACallback.filter(F.action == "list"))
async def handle_list(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await show_interview_qa_list(callback, user, session, i18n)
    await callback.answer()


@router.callback_query(InterviewQACallback.filter(F.action == "base_question"))
async def handle_base_question(
    callback: CallbackQuery,
    callback_data: InterviewQACallback,
    user: User,
    i18n: I18nContext,
) -> None:
    if callback_data.question_key == "why_new_job":
        text = f"<b>{i18n.get('iqa-why-new-job-title')}</b>\n\n{i18n.get('iqa-why-new-job-hint')}"
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                text,
                reply_markup=why_new_job_reasons_keyboard(i18n, is_admin=user.is_admin),
            )
    await callback.answer()


@router.callback_query(InterviewQACallback.filter(F.action == "why_reason_manual"))
async def handle_why_reason_manual(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    if not user.is_admin:
        await callback.answer(i18n.get("access-denied"), show_alert=True)
        return
    await state.set_state(InterviewQAForm.why_reason_manual)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("iqa-enter-reason-manual"),
        )
    await callback.answer()


@router.message(InterviewQAForm.why_reason_manual)
async def handle_why_reason_manual_text(
    message: Message,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    if not user.is_admin:
        await state.clear()
        return
    reason_text = (message.text or "").strip()
    if not reason_text:
        await message.answer(i18n.get("iqa-enter-reason-manual"))
        return
    question_text = i18n.get("iqa-why-new-job-title")
    await state.update_data(
        iqa_add_question=question_text,
        iqa_add_answer=reason_text,
        iqa_add_prev_action="why_reason_manual",
        iqa_add_prev_question_key="why_new_job",
        iqa_add_prev_reason="other",
    )
    text = (
        f"<b>{question_text}</b>\n\n"
        f"<b>{i18n.get('iqa-reason-label')}:</b> {i18n.get('iqa-reason-other')}\n\n"
        f"{reason_text}"
    )
    back_keyboard = answer_back_keyboard(
        question_key="why_new_job", reason="other", i18n=i18n
    )
    await message.answer(text, reply_markup=back_keyboard)


@router.callback_query(InterviewQACallback.filter(F.action == "why_reason"))
async def handle_why_reason(
    callback: CallbackQuery,
    callback_data: InterviewQACallback,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    reason = callback_data.reason
    answer_key = _WHY_REASON_ANSWERS.get(reason, "iqa-why-answer-other")
    answer_text = i18n.get(answer_key)
    question_text = i18n.get("iqa-why-new-job-title")

    await state.update_data(
        iqa_add_question=question_text,
        iqa_add_answer=answer_text,
        iqa_add_prev_action="why_reason",
        iqa_add_prev_question_key="why_new_job",
        iqa_add_prev_reason=reason,
    )

    text = (
        f"<b>{question_text}</b>\n\n"
        f"<b>{i18n.get('iqa-reason-label')}: {i18n.get(f'iqa-reason-{reason}')}</b>\n\n"
        f"{answer_text}"
    )
    back_keyboard = answer_back_keyboard(
        question_key="why_new_job", reason=reason, i18n=i18n
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=back_keyboard)
    await callback.answer()


@router.callback_query(InterviewQACallback.filter(F.action == "view_question"))
async def handle_view_question(
    callback: CallbackQuery,
    callback_data: InterviewQACallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    repo = StandardQuestionRepository(session)
    question = await repo.get_by_key(user.id, callback_data.question_key)
    if not question:
        await callback.answer(i18n.get("iqa-not-found"), show_alert=True)
        return

    await state.update_data(
        iqa_add_question=question.question_text,
        iqa_add_answer=question.answer_text or i18n.get("iqa-no-answer"),
        iqa_add_prev_action="view_question",
        iqa_add_prev_question_key=callback_data.question_key,
        iqa_add_prev_reason="",
    )

    text = f"<b>{question.question_text}</b>\n\n{question.answer_text or i18n.get('iqa-no-answer')}"
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=question_detail_keyboard(callback_data.question_key, i18n),
        )
    await callback.answer()


@router.callback_query(InterviewQACallback.filter(F.action == "generate_all"))
async def handle_generate_all(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    we_repo = WorkExperienceRepository(session)
    if not await we_repo.count_active_by_user(user.id):
        await callback.answer(i18n.get("iqa-no-work-experience"), show_alert=True)
        return

    await callback.answer()

    qa_repo = StandardQuestionRepository(session)
    generated_keys = {q.question_key for q in await qa_repo.get_ai_generated(user.id)}

    text = (
        f"<b>{i18n.get('iqa-generate-select-title')}</b>\n\n"
        f"{i18n.get('iqa-generate-select-description')}"
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=generate_select_keyboard(generated_keys, i18n),
        )


@router.callback_query(InterviewQACallback.filter(F.action == "generate_one"))
async def handle_generate_one(
    callback: CallbackQuery,
    callback_data: InterviewQACallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    we_repo = WorkExperienceRepository(session)
    if not await we_repo.count_active_by_user(user.id):
        await callback.answer(i18n.get("iqa-no-work-experience"), show_alert=True)
        return

    await callback.answer()

    qa_repo = StandardQuestionRepository(session)
    existing = await qa_repo.get_by_key(user.id, callback_data.question_key)
    if existing:
        await qa_repo.soft_delete(existing)
        await session.commit()

    from src.core.celery_async import run_celery_task
    from src.worker.tasks.interview_qa import generate_interview_qa_task

    wait_msg = await callback.message.edit_text(i18n.get("iqa-generating"))
    await run_celery_task(
        generate_interview_qa_task,
        user.id,
        callback.message.chat.id,
        wait_msg.message_id if wait_msg else callback.message.message_id,
        user.language_code or "ru",
        callback_data.question_key,
    )


@router.callback_query(InterviewQACallback.filter(F.action == "generate_pending"))
async def handle_generate_pending(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    we_repo = WorkExperienceRepository(session)
    if not await we_repo.count_active_by_user(user.id):
        await callback.answer(i18n.get("iqa-no-work-experience"), show_alert=True)
        return

    await callback.answer()

    from src.core.celery_async import run_celery_task
    from src.worker.tasks.interview_qa import generate_interview_qa_task

    wait_msg = await callback.message.edit_text(i18n.get("iqa-generating"))
    await run_celery_task(
        generate_interview_qa_task,
        user.id,
        callback.message.chat.id,
        wait_msg.message_id if wait_msg else callback.message.message_id,
        user.language_code or "ru",
    )


@router.callback_query(InterviewQACallback.filter(F.action == "regenerate"))
async def handle_regenerate(
    callback: CallbackQuery,
    callback_data: InterviewQACallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await callback.answer()

    repo = StandardQuestionRepository(session)
    question = await repo.get_by_key(user.id, callback_data.question_key)
    if question:
        await repo.soft_delete(question)
        await session.commit()

    from src.core.celery_async import run_celery_task
    from src.worker.tasks.interview_qa import generate_interview_qa_task

    wait_msg = await callback.message.edit_text(i18n.get("iqa-generating"))
    await run_celery_task(
        generate_interview_qa_task,
        user.id,
        callback.message.chat.id,
        wait_msg.message_id if wait_msg else callback.message.message_id,
        user.language_code or "ru",
        callback_data.question_key,
    )


async def show_interview_list_for_add(
    callback: CallbackQuery,
    user: User,
    i18n: I18nContext,
    session: AsyncSession,
    page: int = 0,
) -> None:
    from src.bot.modules.interviews.services import get_interviews_paginated

    interviews, total = await get_interviews_paginated(session, user.id, page)

    if not interviews and page == 0:
        text = i18n.get("iqa-add-no-interviews")
        kb = interview_add_select_keyboard([], 0, 0, i18n)
    else:
        text = i18n.get("iqa-add-select-title")
        kb = interview_add_select_keyboard(list(interviews), page, total, i18n)

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=kb)


@router.callback_query(InterviewQACallback.filter(F.action == "add_to_interview"))
async def handle_add_to_interview(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    question = data.get("iqa_add_question")
    answer = data.get("iqa_add_answer")
    if not question or not answer:
        await callback.answer(i18n.get("iqa-not-found"), show_alert=True)
        return

    await state.update_data(
        iqa_add_prev_action=data.get("iqa_add_prev_action"),
        iqa_add_prev_question_key=data.get("iqa_add_prev_question_key"),
        iqa_add_prev_reason=data.get("iqa_add_prev_reason", ""),
    )

    await show_interview_list_for_add(callback, user, i18n, session, page=0)
    await callback.answer()


@router.callback_query(InterviewQACallback.filter(F.action == "add_to_interview_list"))
async def handle_add_to_interview_list(
    callback: CallbackQuery,
    callback_data: InterviewQACallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await show_interview_list_for_add(
        callback, user, i18n, session, page=callback_data.page
    )
    await callback.answer()


@router.callback_query(InterviewQACallback.filter(F.action == "add_to_interview_select"))
async def handle_add_to_interview_select(
    callback: CallbackQuery,
    callback_data: InterviewQACallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    question = data.get("iqa_add_question")
    answer = data.get("iqa_add_answer")
    if not question or not answer:
        await callback.answer(i18n.get("iqa-not-found"), show_alert=True)
        return

    from src.repositories.interview import InterviewNoteRepository, InterviewRepository

    interview_repo = InterviewRepository(session)
    interview = await interview_repo.get_by_id(callback_data.interview_id)
    if not interview or interview.user_id != user.id:
        await callback.answer(i18n.get("iqa-not-found"), show_alert=True)
        return

    notes_repo = InterviewNoteRepository(session)
    notes = await notes_repo.get_by_interview(callback_data.interview_id)
    sort_order = len(notes)
    content = f"Q: {question}\n\nA: {answer}"
    await notes_repo.create_note(
        interview_id=callback_data.interview_id,
        content=content,
        sort_order=sort_order,
    )
    await session.commit()

    for key in (
        "iqa_add_question",
        "iqa_add_answer",
        "iqa_add_prev_action",
        "iqa_add_prev_question_key",
        "iqa_add_prev_reason",
    ):
        await state.update_data({key: None})

    await callback.answer(i18n.get("iqa-add-success"))
    await show_interview_qa_list(callback, user, session, i18n)


@router.callback_query(InterviewQACallback.filter(F.action == "add_to_interview_back"))
async def handle_add_to_interview_back(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    prev_action = data.get("iqa_add_prev_action")
    prev_question_key = data.get("iqa_add_prev_question_key")
    prev_reason = data.get("iqa_add_prev_reason", "")
    manual_answer = data.get("iqa_add_answer")

    for key in (
        "iqa_add_question",
        "iqa_add_answer",
        "iqa_add_prev_action",
        "iqa_add_prev_question_key",
        "iqa_add_prev_reason",
    ):
        await state.update_data({key: None})

    if prev_action == "view_question":
        repo = StandardQuestionRepository(session)
        question = await repo.get_by_key(user.id, prev_question_key)
        if not question:
            await show_interview_qa_list(callback, user, session, i18n)
            return
        answer = question.answer_text or i18n.get("iqa-no-answer")
        text = f"<b>{question.question_text}</b>\n\n{answer}"
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                text,
                reply_markup=question_detail_keyboard(prev_question_key, i18n),
            )
        await state.update_data(
            iqa_add_question=question.question_text,
            iqa_add_answer=question.answer_text or i18n.get("iqa-no-answer"),
            iqa_add_prev_action="view_question",
            iqa_add_prev_question_key=prev_question_key,
            iqa_add_prev_reason="",
        )
    elif prev_action == "why_reason":
        answer_key = _WHY_REASON_ANSWERS.get(prev_reason, "iqa-why-answer-other")
        answer_text = i18n.get(answer_key)
        question_text = i18n.get("iqa-why-new-job-title")
        text = (
            f"<b>{question_text}</b>\n\n"
            f"<b>{i18n.get('iqa-reason-label')}: {i18n.get(f'iqa-reason-{prev_reason}')}</b>\n\n"
            f"{answer_text}"
        )
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                text,
                reply_markup=answer_back_keyboard(
                    question_key="why_new_job", reason=prev_reason, i18n=i18n
                ),
            )
        await state.update_data(
            iqa_add_question=question_text,
            iqa_add_answer=answer_text,
            iqa_add_prev_action="why_reason",
            iqa_add_prev_question_key="why_new_job",
            iqa_add_prev_reason=prev_reason,
        )
    elif prev_action == "why_reason_manual":
        manual_text = manual_answer
        if not manual_text:
            await show_interview_qa_list(callback, user, session, i18n)
            return
        question_text = i18n.get("iqa-why-new-job-title")
        text = (
            f"<b>{question_text}</b>\n\n"
            f"<b>{i18n.get('iqa-reason-label')}:</b> {i18n.get('iqa-reason-other')}\n\n"
            f"{manual_text}"
        )
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                text,
                reply_markup=answer_back_keyboard(
                    question_key="why_new_job", reason="other", i18n=i18n
                ),
            )
        await state.update_data(
            iqa_add_question=question_text,
            iqa_add_answer=manual_text,
            iqa_add_prev_action="why_reason_manual",
            iqa_add_prev_question_key="why_new_job",
            iqa_add_prev_reason="other",
        )
    else:
        await show_interview_qa_list(callback, user, session, i18n)

    await callback.answer()
