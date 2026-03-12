"""Handlers for the Resume Generator module.

This module orchestrates existing features:
1. Edit work experiences (via shared work_experience module)
2. Generate key phrases (via ai tasks)
3. Generate vacancy summary (via vacancy_summary module)
4. Show proceed view
5. Show final resume with "Create autoparser from resume" option
"""

from __future__ import annotations

import contextlib

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.modules.resume.callbacks import ResumeCallback
from src.bot.modules.resume.keyboards import (
    resume_cancel_keyboard,
    resume_keywords_source_keyboard,
    resume_parsing_companies_keyboard,
    resume_result_keyboard,
    resume_start_keyboard,
)
from src.bot.modules.resume.states import ResumeForm
from src.core.i18n import I18nContext
from src.models.user import User

router = Router(name="resume")


@router.callback_query(ResumeCallback.filter(F.action == "start"))
async def handle_start(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await state.clear()
    from src.bot.modules.work_experience.handlers import show_work_experience

    await show_work_experience(
        callback.message,
        user,
        "resume_step1",
        session,
        i18n,
        show_continue=True,
        show_skip=True,
    )
    await callback.answer()


@router.callback_query(ResumeCallback.filter(F.action == "cancel"))
async def handle_cancel(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.clear()
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("res-cancelled"),
            reply_markup=resume_start_keyboard(i18n),
        )
    await callback.answer()


@router.callback_query(ResumeCallback.filter(F.action == "step2_keyphrases"))
async def handle_step2_keyphrases(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.bot.modules.parsing import services as we_service

    experiences = await we_service.get_active_work_experiences(session, user.id)
    if not experiences:
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("res-no-experiences"),
                reply_markup=resume_cancel_keyboard(i18n),
            )
        await callback.answer()
        return

    await state.update_data(
        res_chat_id=callback.message.chat.id,
        res_message_id=callback.message.message_id,
    )

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("res-keywords-source-prompt"),
            reply_markup=resume_keywords_source_keyboard(i18n),
        )
    await callback.answer()


@router.callback_query(ResumeCallback.filter(F.action == "keywords_skip"))
async def handle_keywords_skip(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    from src.worker.tasks.work_experience import generate_resume_key_phrases_task

    wait_msg = None
    with contextlib.suppress(TelegramBadRequest):
        wait_msg = await callback.message.edit_text(
            i18n.get("res-generating-keyphrases"),
            reply_markup=resume_cancel_keyboard(i18n),
        )

    generate_resume_key_phrases_task.delay(
        user_id=user.id,
        chat_id=callback.message.chat.id,
        message_id=wait_msg.message_id if wait_msg else callback.message.message_id,
        locale=user.language_code or "ru",
    )
    await callback.answer()


@router.callback_query(ResumeCallback.filter(F.action == "keywords_manual"))
async def handle_keywords_manual(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.set_state(ResumeForm.entering_keywords)
    await state.update_data(
        res_chat_id=callback.message.chat.id,
        res_message_id=callback.message.message_id,
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("res-keywords-enter-prompt"),
            reply_markup=resume_cancel_keyboard(i18n),
        )
    await callback.answer()


@router.message(StateFilter(ResumeForm.entering_keywords))
async def handle_keywords_typed(
    message: Message,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    from src.worker.tasks.work_experience import generate_resume_key_phrases_task

    raw = message.text or ""
    keywords = [kw.strip() for kw in raw.split(",") if kw.strip()]

    await state.clear()

    wait_msg = await message.answer(i18n.get("res-generating-keyphrases"))

    generate_resume_key_phrases_task.delay(
        user_id=user.id,
        chat_id=message.chat.id,
        message_id=wait_msg.message_id,
        locale=user.language_code or "ru",
        extra_keywords=keywords,
    )


@router.callback_query(ResumeCallback.filter(F.action == "keywords_from_parsing"))
async def handle_keywords_from_parsing(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.repositories.parsing import AggregatedResultRepository, ParsingCompanyRepository

    company_repo = ParsingCompanyRepository(session)
    agg_repo = AggregatedResultRepository(session)

    companies = await company_repo.get_by_user(user.id, limit=50)

    companies_with_keywords = []
    for company in companies:
        agg = await agg_repo.get_by_company(company.id)
        if agg and agg.top_keywords:
            companies_with_keywords.append(company)

    if not companies_with_keywords:
        wait_msg = None
        with contextlib.suppress(TelegramBadRequest):
            wait_msg = await callback.message.edit_text(
                i18n.get("res-keywords-no-parsings"),
            )
        from src.worker.tasks.work_experience import generate_resume_key_phrases_task

        generate_resume_key_phrases_task.delay(
            user_id=user.id,
            chat_id=callback.message.chat.id,
            message_id=wait_msg.message_id if wait_msg else callback.message.message_id,
            locale=user.language_code or "ru",
        )
        await callback.answer()
        return

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("res-select-parsing-company"),
            reply_markup=resume_parsing_companies_keyboard(companies_with_keywords, i18n),
        )
    await callback.answer()


@router.callback_query(ResumeCallback.filter(F.action == "keywords_use_company"))
async def handle_keywords_use_company(
    callback: CallbackQuery,
    callback_data: ResumeCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.repositories.parsing import AggregatedResultRepository
    from src.worker.tasks.work_experience import generate_resume_key_phrases_task

    agg_repo = AggregatedResultRepository(session)
    agg = await agg_repo.get_by_company(callback_data.company_id)

    main_keywords: list[str] = []
    secondary_keywords: list[str] = []

    if agg and agg.top_keywords:
        sorted_kws = sorted(agg.top_keywords.items(), key=lambda x: x[1], reverse=True)
        main_keywords = [kw for kw, _ in sorted_kws[:30]]
        secondary_keywords = [kw for kw, _ in sorted_kws[30:60]]

    wait_msg = None
    with contextlib.suppress(TelegramBadRequest):
        wait_msg = await callback.message.edit_text(
            i18n.get("res-generating-keyphrases"),
            reply_markup=resume_cancel_keyboard(i18n),
        )

    generate_resume_key_phrases_task.delay(
        user_id=user.id,
        chat_id=callback.message.chat.id,
        message_id=wait_msg.message_id if wait_msg else callback.message.message_id,
        locale=user.language_code or "ru",
        extra_keywords=main_keywords,
        secondary_keywords=secondary_keywords,
    )
    await callback.answer()


@router.callback_query(ResumeCallback.filter(F.action == "step3_summary"))
async def handle_step3_summary(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    from src.bot.modules.vacancy_summary.handlers import show_vacancy_summary_list

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("res-step3-summary"),
            reply_markup=resume_cancel_keyboard(i18n),
        )

    await show_vacancy_summary_list(callback, user, None, i18n)
    await callback.answer()


@router.callback_query(ResumeCallback.filter(F.action == "show_result"))
async def handle_show_result(
    callback: CallbackQuery,
    callback_data: ResumeCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.bot.modules.parsing import services as we_service
    from src.repositories.vacancy_summary import VacancySummaryRepository

    experiences = await we_service.get_active_work_experiences(session, user.id)
    vs_repo = VacancySummaryRepository(session)
    summaries, _ = await vs_repo.get_by_user_paginated(user.id, 0)
    latest_summary = summaries[0] if summaries else None

    lines = [f"<b>{i18n.get('res-result-title')}</b>", ""]

    if experiences:
        lines.append(f"<b>{i18n.get('res-work-experiences')}</b>")
        for e in experiences:
            lines.append(f"  • <b>{e.company_name}</b> — {e.stack}")
        lines.append("")

    if latest_summary and latest_summary.generated_text:
        lines.append(f"<b>{i18n.get('res-about-me')}</b>")
        text = latest_summary.generated_text
        if len(text) > 1000:
            text = text[:950] + "..."
        lines.append(text)
        lines.append("")

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=resume_result_keyboard(i18n),
        )
    await callback.answer()


async def handle_resume_work_exp_done(callback: CallbackQuery, i18n: I18nContext) -> None:
    """Called by work_experience module when done editing for resume flow."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("res-btn-generate-keyphrases"),
                    callback_data=ResumeCallback(action="step2_keyphrases").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-skip"),
                    callback_data=ResumeCallback(action="step3_summary").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=ResumeCallback(action="cancel").pack(),
                )
            ],
        ]
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(i18n.get("res-step2-keyphrases"), reply_markup=keyboard)


@router.callback_query(ResumeCallback.filter(F.action == "create_autoparser"))
async def handle_create_autoparser(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    from src.bot.modules.autoparse.handlers import autoparse_creation_start

    await autoparse_creation_start(callback, user, session, state, i18n)
    await callback.answer()
