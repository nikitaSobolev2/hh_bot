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
    generate_select_keyboard,
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
    await state.clear()
    text = (
        f"<b>{i18n.get('iqa-why-new-job-title')}</b>\n\n"
        f"<b>{i18n.get('iqa-reason-label')}:</b> {i18n.get('iqa-reason-other')}\n\n"
        f"{reason_text}"
    )
    back_keyboard = _back_to_list_keyboard(i18n)
    await message.answer(text, reply_markup=back_keyboard)


@router.callback_query(InterviewQACallback.filter(F.action == "why_reason"))
async def handle_why_reason(
    callback: CallbackQuery,
    callback_data: InterviewQACallback,
    i18n: I18nContext,
) -> None:
    reason = callback_data.reason
    answer_key = _WHY_REASON_ANSWERS.get(reason, "iqa-why-answer-other")
    answer_text = i18n.get(answer_key)

    text = (
        f"<b>{i18n.get('iqa-why-new-job-title')}</b>\n\n"
        f"<b>{i18n.get('iqa-reason-label')}: {i18n.get(f'iqa-reason-{reason}')}</b>\n\n"
        f"{answer_text}"
    )
    back_keyboard = _back_to_list_keyboard(i18n)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=back_keyboard)
    await callback.answer()


@router.callback_query(InterviewQACallback.filter(F.action == "view_question"))
async def handle_view_question(
    callback: CallbackQuery,
    callback_data: InterviewQACallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    repo = StandardQuestionRepository(session)
    question = await repo.get_by_key(user.id, callback_data.question_key)
    if not question:
        await callback.answer(i18n.get("iqa-not-found"), show_alert=True)
        return

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


def _back_to_list_keyboard(i18n: I18nContext):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=InterviewQACallback(action="list").pack(),
                )
            ]
        ]
    )
