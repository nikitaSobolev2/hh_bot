"""Handlers for the Resume Generator module.

7-step resume generation wizard:
  1. Ask for job title (vacancy name)
  2. Ask for skill level
  3. Review / edit work experiences; disable any for this session
  4. Pick parsing company for keyword integration (skippable)
  5. Generate key phrases (skippable)
  6. Generate / select summary (skippable)
  7. Generate recommendation letters per job (skippable per job)
  Final: show structured result with per-section navigation buttons
"""

from __future__ import annotations

import contextlib

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.modules.resume.callbacks import ResumeCallback
from src.bot.modules.resume.keyboards import (
    resume_cancel_keyboard,
    resume_job_view_keyboard,
    resume_keywords_source_keyboard,
    resume_list_keyboard,
    resume_parsing_companies_keyboard,
    resume_rec_character_keyboard,
    resume_rec_focus_keyboard,
    resume_rec_letter_ask_keyboard,
    resume_result_keyboard,
    resume_skill_level_buttons,
    resume_start_keyboard,
)
from src.bot.modules.resume.states import ResumeForm
from src.core.i18n import I18nContext
from src.models.user import User
from src.services.ai.prompts import REC_LETTER_CHARACTERS

router = Router(name="resume")

_SKILL_LEVELS = ["Junior", "Middle", "Senior", "Lead"]


# ── Resume hub: list and view ──────────────────────────────────────────────────


async def show_resume_list(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
    page: int = 0,
) -> None:
    from src.repositories.resume import ResumeRepository

    repo = ResumeRepository(session)
    resumes, total = await repo.get_by_user_paginated(user.id, page)

    text = i18n.get("res-list-empty") if not resumes and page == 0 else i18n.get("res-list-title")
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=resume_list_keyboard(resumes, page, total, i18n),
        )


@router.callback_query(ResumeCallback.filter(F.action == "list"))
async def handle_resume_list(
    callback: CallbackQuery,
    callback_data: ResumeCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await show_resume_list(callback, user, session, i18n, callback_data.page)
    await callback.answer()


@router.callback_query(ResumeCallback.filter(F.action == "view"))
async def handle_resume_view(
    callback: CallbackQuery,
    callback_data: ResumeCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    """Show an existing resume's result view."""
    resume_id = callback_data.work_exp_id
    from src.repositories.recommendation_letter import RecommendationLetterRepository
    from src.repositories.resume import ResumeRepository

    repo = ResumeRepository(session)
    resume = await repo.get_by_id(resume_id)
    if not resume or resume.user_id != user.id or resume.is_deleted:
        await callback.answer(i18n.get("res-not-found"), show_alert=True)
        return

    await state.update_data(res_resume_id=resume_id, res_viewing_from_list=True)

    letter_repo = RecommendationLetterRepository(session)
    letters = await letter_repo.get_by_resume(resume_id)

    lines = _build_result_text(resume, i18n)
    locale = user.language_code or "ru"

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=resume_result_keyboard(resume, letters, locale, i18n, from_list=True),
        )
    await callback.answer()


# ── Step 0: entry point (create new) ────────────────────────────────────────────


@router.callback_query(ResumeCallback.filter(F.action == "start"))
async def handle_start(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.clear()
    await state.set_state(ResumeForm.job_title)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("res-enter-job-title"),
            reply_markup=resume_cancel_keyboard(i18n),
        )
    await callback.answer()


# ── Step 1: job title ─────────────────────────────────────────────────────────


@router.message(StateFilter(ResumeForm.job_title))
async def fsm_job_title(
    message: Message,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer(i18n.get("res-job-title-required"))
        return
    await state.update_data(res_job_title=title)
    await state.set_state(ResumeForm.skill_level)
    await message.answer(
        i18n.get("res-enter-skill-level"),
        reply_markup=resume_skill_level_buttons(i18n),
    )


# ── Step 2: skill level (buttons or free text) ────────────────────────────────


@router.callback_query(ResumeCallback.filter(F.action == "set_skill_level"))
async def handle_set_skill_level(
    callback: CallbackQuery,
    callback_data: ResumeCallback,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    idx = callback_data.work_exp_id  # 1-based index into _SKILL_LEVELS
    level = _SKILL_LEVELS[idx - 1] if 1 <= idx <= len(_SKILL_LEVELS) else None
    await state.update_data(res_skill_level=level)
    await _show_work_experience_step(callback, user, state, session, i18n)
    await callback.answer()


@router.callback_query(ResumeCallback.filter(F.action == "skip_skill_level"))
async def handle_skip_skill_level(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await state.update_data(res_skill_level=None)
    await _show_work_experience_step(callback, user, state, session, i18n)
    await callback.answer()


@router.message(StateFilter(ResumeForm.skill_level))
async def fsm_skill_level(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    level = (message.text or "").strip() or None
    await state.update_data(res_skill_level=level)
    await _show_work_experience_list_message(message, user, state, session, i18n)


async def _show_work_experience_step(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.bot.modules.work_experience.handlers import show_work_experience

    data = await state.get_data()
    disabled_ids: list[int] = data.get("res_disabled_exp_ids") or []
    await show_work_experience(
        callback.message,
        user,
        "resume_step1",
        session,
        i18n,
        show_continue=True,
        show_skip=True,
        disabled_exp_ids=set(disabled_ids),
    )


async def _show_work_experience_list_message(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.bot.modules.work_experience.handlers import show_work_experience

    data = await state.get_data()
    disabled_ids: list[int] = data.get("res_disabled_exp_ids") or []
    await show_work_experience(
        message,
        user,
        "resume_step1",
        session,
        i18n,
        edit=False,
        show_continue=True,
        show_skip=True,
        disabled_exp_ids=set(disabled_ids),
    )


# ── Step 2 → 3: work experience session-toggle ───────────────────────────────


@router.callback_query(ResumeCallback.filter(F.action == "toggle_exp"))
async def handle_toggle_exp(
    callback: CallbackQuery,
    callback_data: ResumeCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    exp_id = callback_data.work_exp_id
    data = await state.get_data()
    disabled: list[int] = list(data.get("res_disabled_exp_ids") or [])
    if exp_id in disabled:
        disabled.remove(exp_id)
    else:
        disabled.append(exp_id)
    await state.update_data(res_disabled_exp_ids=disabled)
    await _show_work_experience_step(callback, user, state, session, i18n)
    await callback.answer()


# ── Step 3: keyphrases ────────────────────────────────────────────────────────


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

    data = await state.get_data()
    resume_id: int | None = data.get("res_resume_id")
    job_title: str | None = data.get("res_job_title")
    skill_level: str | None = data.get("res_skill_level")
    disabled_ids: list[int] = data.get("res_disabled_exp_ids") or []

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
        resume_id=resume_id,
        job_title=job_title,
        skill_level=skill_level,
        disabled_exp_ids=disabled_ids,
    )
    await callback.answer()


@router.callback_query(ResumeCallback.filter(F.action == "keywords_manual"))
async def handle_keywords_manual(
    callback: CallbackQuery,
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

    data = await state.get_data()
    resume_id: int | None = data.get("res_resume_id")
    job_title: str | None = data.get("res_job_title")
    skill_level: str | None = data.get("res_skill_level")
    disabled_ids: list[int] = data.get("res_disabled_exp_ids") or []

    # Use set_state(None) instead of clear() to preserve accumulated wizard data
    await state.set_state(None)

    wait_msg = await message.answer(i18n.get("res-generating-keyphrases"))

    generate_resume_key_phrases_task.delay(
        user_id=user.id,
        chat_id=message.chat.id,
        message_id=wait_msg.message_id,
        locale=user.language_code or "ru",
        extra_keywords=keywords,
        resume_id=resume_id,
        job_title=job_title,
        skill_level=skill_level,
        disabled_exp_ids=disabled_ids,
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
    from src.worker.tasks.work_experience import generate_resume_key_phrases_task

    company_repo = ParsingCompanyRepository(session)
    agg_repo = AggregatedResultRepository(session)

    companies = await company_repo.get_by_user(user.id, limit=50)

    companies_with_keywords = []
    for company in companies:
        agg = await agg_repo.get_by_company(company.id)
        if agg and agg.top_keywords:
            companies_with_keywords.append(company)

    if not companies_with_keywords:
        data = await state.get_data()
        resume_id = data.get("res_resume_id")
        job_title = data.get("res_job_title")
        skill_level = data.get("res_skill_level")
        disabled_ids: list[int] = data.get("res_disabled_exp_ids") or []

        wait_msg = None
        with contextlib.suppress(TelegramBadRequest):
            wait_msg = await callback.message.edit_text(i18n.get("res-keywords-no-parsings"))

        generate_resume_key_phrases_task.delay(
            user_id=user.id,
            chat_id=callback.message.chat.id,
            message_id=wait_msg.message_id if wait_msg else callback.message.message_id,
            locale=user.language_code or "ru",
            resume_id=resume_id,
            job_title=job_title,
            skill_level=skill_level,
            disabled_exp_ids=disabled_ids,
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
    parsed_keywords_dict: dict | None = None

    if agg and agg.top_keywords:
        sorted_kws = sorted(agg.top_keywords.items(), key=lambda x: x[1], reverse=True)
        main_keywords = [kw for kw, _ in sorted_kws[:30]]
        secondary_keywords = [kw for kw, _ in sorted_kws[30:60]]
        parsed_keywords_dict = dict(sorted_kws)

    data = await state.get_data()
    resume_id: int | None = data.get("res_resume_id")
    job_title: str | None = data.get("res_job_title")
    skill_level: str | None = data.get("res_skill_level")
    disabled_ids: list[int] = data.get("res_disabled_exp_ids") or []

    # Save parsed keywords to Resume record so they appear in final result
    if resume_id and parsed_keywords_dict:
        from src.repositories.resume import ResumeRepository

        resume_repo = ResumeRepository(session)
        resume = await resume_repo.get_by_id(resume_id)
        if resume:
            await resume_repo.update(resume, parsed_keywords=parsed_keywords_dict)
            await session.commit()

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
        resume_id=resume_id,
        job_title=job_title,
        skill_level=skill_level,
        disabled_exp_ids=disabled_ids,
    )
    await callback.answer()


# ── Step 3 (continue after keyphrases) / step 6 (summary) ────────────────────


@router.callback_query(ResumeCallback.filter(F.action == "step3_summary"))
async def handle_step3_summary(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.bot.modules.vacancy_summary.handlers import show_vacancy_summary_list

    await state.update_data(vs_resume_flow=True)
    await show_vacancy_summary_list(callback, user, session, i18n, state=state)
    await callback.answer()


@router.callback_query(ResumeCallback.filter(F.action == "select_summary"))
async def handle_select_summary(
    callback: CallbackQuery,
    callback_data: ResumeCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    """User picked an existing summary for their resume from the summary detail view."""
    summary_id = callback_data.summary_id
    resume_id = await _ensure_resume_record(state, session, user.id)

    from src.repositories.resume import ResumeRepository

    resume_repo = ResumeRepository(session)
    resume = await resume_repo.get_by_id(resume_id)
    if resume:
        await resume_repo.update(resume, summary_id=summary_id)
        await session.commit()

    await state.update_data(vs_resume_flow=False)
    await _start_rec_letters_flow(callback, user, state, session, i18n)
    await callback.answer()


@router.callback_query(ResumeCallback.filter(F.action == "skip_to_rec_letters"))
async def handle_skip_to_rec_letters(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await _start_rec_letters_flow(callback, user, state, session, i18n)
    await callback.answer()


# ── Step 7: recommendation letters ───────────────────────────────────────────


async def _start_rec_letters_flow(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.bot.modules.parsing import services as we_service

    data = await state.get_data()
    disabled_ids: set[int] = set(data.get("res_disabled_exp_ids") or [])

    all_experiences = await we_service.get_active_work_experiences(session, user.id)
    enabled = [e for e in all_experiences if e.id not in disabled_ids]

    if not enabled:
        await _show_final_result(callback, user, state, session, i18n)
        return

    queue = [e.id for e in enabled]
    await state.update_data(res_rec_letter_queue=queue)
    await _ask_rec_letter_for_next(callback, state, session, i18n, queue[0])


async def _ask_rec_letter_for_next(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
    work_exp_id: int,
) -> None:
    from src.repositories.work_experience import WorkExperienceRepository

    repo = WorkExperienceRepository(session)
    exp = await repo.get_by_id(work_exp_id)
    company_name = exp.company_name if exp else str(work_exp_id)

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("res-ask-rec-letter", company=company_name),
            reply_markup=resume_rec_letter_ask_keyboard(work_exp_id, i18n),
        )


@router.callback_query(ResumeCallback.filter(F.action == "rec_start"))
async def handle_rec_start(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await _start_rec_letters_flow(callback, user, state, session, i18n)
    await callback.answer()


@router.callback_query(ResumeCallback.filter(F.action == "rec_next"))
async def handle_rec_next(
    callback: CallbackQuery,
    callback_data: ResumeCallback,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await _ask_rec_letter_for_next(callback, state, session, i18n, callback_data.work_exp_id)
    await callback.answer()


@router.callback_query(ResumeCallback.filter(F.action == "rec_no"))
async def handle_rec_no(
    callback: CallbackQuery,
    callback_data: ResumeCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await _advance_rec_queue(callback, callback_data.work_exp_id, user, state, session, i18n)
    await callback.answer()


@router.callback_query(ResumeCallback.filter(F.action == "rec_yes"))
async def handle_rec_yes(
    callback: CallbackQuery,
    callback_data: ResumeCallback,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.update_data(res_current_rec_exp_id=callback_data.work_exp_id)
    await state.set_state(ResumeForm.rec_speaker_name)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("res-rec-enter-speaker-name"),
            reply_markup=resume_cancel_keyboard(i18n),
        )
    await callback.answer()


@router.message(StateFilter(ResumeForm.rec_speaker_name))
async def fsm_rec_speaker_name(
    message: Message,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer(i18n.get("res-rec-speaker-name-required"))
        return
    await state.update_data(res_rec_speaker_name=name)
    await state.set_state(ResumeForm.rec_speaker_position)
    data = await state.get_data()
    work_exp_id = data.get("res_current_rec_exp_id", 0)
    await message.answer(
        i18n.get("res-rec-enter-speaker-position"),
        reply_markup=_rec_skip_position_keyboard(work_exp_id, i18n),
    )


def _rec_skip_position_keyboard(work_exp_id: int, i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-skip"),
                    callback_data=ResumeCallback(
                        action="rec_skip_position",
                        work_exp_id=work_exp_id,
                    ).pack(),
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


@router.message(StateFilter(ResumeForm.rec_speaker_position))
async def fsm_rec_speaker_position(
    message: Message,
    state: FSMContext,
    user: User,
    i18n: I18nContext,
) -> None:
    position = (message.text or "").strip() or None
    await state.update_data(res_rec_speaker_position=position)
    data = await state.get_data()
    work_exp_id = data.get("res_current_rec_exp_id", 0)
    await message.answer(
        i18n.get("res-rec-pick-character"),
        reply_markup=resume_rec_character_keyboard(work_exp_id, user.language_code or "ru", i18n),
    )


@router.callback_query(ResumeCallback.filter(F.action == "rec_skip_position"))
async def handle_rec_skip_position(
    callback: CallbackQuery,
    callback_data: ResumeCallback,
    state: FSMContext,
    user: User,
    i18n: I18nContext,
) -> None:
    await state.update_data(res_rec_speaker_position=None)
    work_exp_id = callback_data.work_exp_id
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("res-rec-pick-character"),
            reply_markup=resume_rec_character_keyboard(
                work_exp_id, user.language_code or "ru", i18n
            ),
        )
    await callback.answer()


@router.callback_query(
    ResumeCallback.filter(F.action.startswith("rec_char_"))  # type: ignore[attr-defined]
)
async def handle_rec_char(
    callback: CallbackQuery,
    callback_data: ResumeCallback,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    character_key = callback_data.action.removeprefix("rec_char_")
    if character_key not in REC_LETTER_CHARACTERS:
        await callback.answer()
        return
    await state.update_data(res_rec_character=character_key)
    work_exp_id = callback_data.work_exp_id
    await state.set_state(ResumeForm.rec_focus)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("res-rec-enter-focus"),
            reply_markup=resume_rec_focus_keyboard(work_exp_id, i18n),
        )
    await callback.answer()


@router.message(StateFilter(ResumeForm.rec_focus))
async def fsm_rec_focus(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    focus = (message.text or "").strip() or None
    await state.update_data(res_rec_focus=focus)
    await _dispatch_rec_letter(message, user, state, session, i18n)


@router.callback_query(ResumeCallback.filter(F.action == "rec_skip_focus"))
async def handle_rec_skip_focus(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await state.update_data(res_rec_focus=None)
    await _dispatch_rec_letter(callback.message, user, state, session, i18n, edit=True)
    await callback.answer()


async def _dispatch_rec_letter(
    message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
    *,
    edit: bool = False,
) -> None:
    from src.repositories.recommendation_letter import RecommendationLetterRepository
    from src.worker.tasks.recommendation_letter import generate_recommendation_letter_task

    data = await state.get_data()
    work_exp_id: int = data.get("res_current_rec_exp_id", 0)
    resume_id: int | None = data.get("res_resume_id")
    speaker_name: str = data.get("res_rec_speaker_name", "")
    speaker_position: str | None = data.get("res_rec_speaker_position")
    character: str = data.get("res_rec_character", "professionalism")
    focus: str | None = data.get("res_rec_focus")

    await state.set_state(None)

    letter_repo = RecommendationLetterRepository(session)
    letter = await letter_repo.create(
        resume_id=resume_id or 0,
        work_experience_id=work_exp_id,
        speaker_name=speaker_name,
        character=character,
        speaker_position=speaker_position,
        focus_text=focus,
    )
    await session.commit()

    # Determine next job in the queue
    queue: list[int] = data.get("res_rec_letter_queue") or []
    next_exp_id: int | None = None
    if work_exp_id in queue:
        idx = queue.index(work_exp_id)
        if idx + 1 < len(queue):
            next_exp_id = queue[idx + 1]

    if edit:
        wait_msg = await message.edit_text(i18n.get("res-rec-generating"))
    else:
        wait_msg = await message.answer(i18n.get("res-rec-generating"))

    generate_recommendation_letter_task.delay(
        letter_id=letter.id,
        user_id=user.id,
        chat_id=message.chat.id,
        message_id=wait_msg.message_id if wait_msg else message.message_id,
        locale=user.language_code or "ru",
        next_work_exp_id=next_exp_id,
        resume_id=resume_id,
    )


async def _advance_rec_queue(
    callback: CallbackQuery,
    current_work_exp_id: int,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    queue: list[int] = data.get("res_rec_letter_queue") or []
    if current_work_exp_id in queue:
        idx = queue.index(current_work_exp_id)
        if idx + 1 < len(queue):
            await _ask_rec_letter_for_next(callback, state, session, i18n, queue[idx + 1])
            return
    await _show_final_result(callback, user, state, session, i18n)


# ── Cancel ────────────────────────────────────────────────────────────────────


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


# ── Final result ──────────────────────────────────────────────────────────────


async def _show_final_result(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.repositories.recommendation_letter import RecommendationLetterRepository
    from src.repositories.resume import ResumeRepository

    data = await state.get_data()
    resume_id: int | None = data.get("res_resume_id")

    resume = None
    letters: list = []
    if resume_id:
        repo = ResumeRepository(session)
        resume = await repo.get_by_id(resume_id)
        if resume:
            letter_repo = RecommendationLetterRepository(session)
            letters = await letter_repo.get_by_resume(resume_id)

    if not resume:
        # Fallback: show a simple done message if no resume record
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("res-result-title"),
                reply_markup=resume_start_keyboard(i18n),
            )
        return

    from_list = bool(data.get("res_viewing_from_list"))

    lines = _build_result_text(resume, i18n)
    locale = user.language_code or "ru"

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=resume_result_keyboard(resume, letters, locale, i18n, from_list=from_list),
        )


@router.callback_query(ResumeCallback.filter(F.action == "show_result"))
async def handle_show_result(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await _show_final_result(callback, user, state, session, i18n)
    await callback.answer()


@router.callback_query(ResumeCallback.filter(F.action == "delete"))
async def handle_resume_delete(
    callback: CallbackQuery,
    callback_data: ResumeCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    resume_id = callback_data.work_exp_id
    from src.repositories.resume import ResumeRepository

    repo = ResumeRepository(session)
    resume = await repo.get_by_id(resume_id)
    if not resume or resume.user_id != user.id or resume.is_deleted:
        await callback.answer(i18n.get("res-not-found"), show_alert=True)
        return

    await repo.soft_delete(resume)
    await session.commit()
    await state.update_data(res_resume_id=None, res_viewing_from_list=False)
    await callback.answer(i18n.get("res-deleted"))
    await show_resume_list(callback, user, session, i18n)


def _build_result_text(resume, i18n: I18nContext) -> list[str]:
    lines = [f"<b>{i18n.get('res-result-title')}</b>", ""]
    lines.append(f"<b>{i18n.get('res-label-job-title')}</b>: {resume.job_title}")
    if resume.skill_level:
        lines.append(f"<b>{i18n.get('res-label-skill-level')}</b>: {resume.skill_level}")
    lines.append("")
    return lines


# ── Result sub-views ──────────────────────────────────────────────────────────


@router.callback_query(ResumeCallback.filter(F.action == "show_keywords"))
async def handle_show_keywords(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.repositories.resume import ResumeRepository

    data = await state.get_data()
    resume_id: int | None = data.get("res_resume_id")
    resume = await ResumeRepository(session).get_by_id(resume_id) if resume_id else None

    if not resume or not resume.parsed_keywords:
        await callback.answer(i18n.get("res-no-keywords"), show_alert=True)
        return

    kw_list = sorted(resume.parsed_keywords.items(), key=lambda x: x[1], reverse=True)
    text = "\n".join(f"- <code>{kw}</code> ({cnt})" for kw, cnt in kw_list[:50])
    back_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=ResumeCallback(action="show_result").pack(),
                )
            ]
        ]
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            f"<b>{i18n.get('res-parsed-keywords-title')}</b>\n\n{text}",
            reply_markup=back_kb,
        )
    await callback.answer()


@router.callback_query(ResumeCallback.filter(F.action == "show_job_view"))
async def handle_show_job_view(
    callback: CallbackQuery,
    callback_data: ResumeCallback,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    """Show per-job detail: keyphrases + recommendation letter buttons.

    company_id field is overloaded here to carry the resume_id.
    work_exp_id carries the work_experience_id (0 when navigating from list).
    """
    from src.repositories.recommendation_letter import RecommendationLetterRepository
    from src.repositories.resume import ResumeRepository

    resume_id = callback_data.company_id
    work_exp_id = callback_data.work_exp_id

    resume = await ResumeRepository(session).get_by_id(resume_id)
    if not resume:
        await callback.answer()
        return

    # Determine which company this button refers to by matching work_exp to keyphrases
    company_name: str | None = None
    letter_id: int | None = None

    if resume.keyphrases_by_company and work_exp_id:
        from src.repositories.work_experience import WorkExperienceRepository

        exp = await WorkExperienceRepository(session).get_by_id(work_exp_id)
        if exp:
            company_name = exp.company_name
            letter_repo = RecommendationLetterRepository(session)
            letter = await letter_repo.get_by_resume_and_work_exp(resume_id, work_exp_id)
            if letter:
                letter_id = letter.id

    if not company_name:
        await callback.answer()
        return

    keyphrases = (resume.keyphrases_by_company or {}).get(company_name, "")
    text = (
        f"<b>💼 {company_name}</b>\n\n{keyphrases}" if keyphrases else f"<b>💼 {company_name}</b>"
    )

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=resume_job_view_keyboard(resume_id, company_name, letter_id, i18n),
        )
    await callback.answer()


@router.callback_query(ResumeCallback.filter(F.action == "show_job_keyphrases"))
async def handle_show_job_keyphrases(
    callback: CallbackQuery,
    callback_data: ResumeCallback,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    """Show keyphrases for a single company.

    company_id carries the resume_id.
    work_exp_id carries the 0-based index of the company in keyphrases_by_company.
    """
    from src.repositories.resume import ResumeRepository

    resume_id = callback_data.company_id
    company_index = callback_data.work_exp_id

    resume = await ResumeRepository(session).get_by_id(resume_id)
    if not resume or not resume.keyphrases_by_company:
        await callback.answer(i18n.get("res-no-keyphrases"), show_alert=True)
        return

    company_names = list(resume.keyphrases_by_company.keys())
    if company_index >= len(company_names):
        await callback.answer(i18n.get("res-no-keyphrases"), show_alert=True)
        return

    company_name = company_names[company_index]
    phrases = resume.keyphrases_by_company[company_name]

    back_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=ResumeCallback(action="show_result").pack(),
                )
            ]
        ]
    )
    text = f"<b>💼 {company_name}</b>\n\n{phrases}"
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text[:4096], reply_markup=back_kb)
    await callback.answer()


@router.callback_query(ResumeCallback.filter(F.action == "show_summary"))
async def handle_show_summary(
    callback: CallbackQuery,
    callback_data: ResumeCallback,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.repositories.vacancy_summary import VacancySummaryRepository

    repo = VacancySummaryRepository(session)
    summary = await repo.get_by_id(callback_data.summary_id)
    if not summary or not summary.generated_text:
        await callback.answer(i18n.get("vs-not-found"), show_alert=True)
        return

    text = summary.generated_text
    if len(text) > 3800:
        text = text[:3800] + "\n..."

    back_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=ResumeCallback(action="show_result").pack(),
                )
            ]
        ]
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=back_kb)
    await callback.answer()


@router.callback_query(ResumeCallback.filter(F.action == "show_rec_letter"))
async def handle_show_rec_letter(
    callback: CallbackQuery,
    callback_data: ResumeCallback,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.repositories.recommendation_letter import RecommendationLetterRepository

    repo = RecommendationLetterRepository(session)
    letter = await repo.get_by_id(callback_data.work_exp_id)
    if not letter or not letter.generated_text:
        await callback.answer(i18n.get("res-rec-letter-not-found"), show_alert=True)
        return

    text = letter.generated_text
    if len(text) > 3800:
        text = text[:3800] + "\n..."

    back_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=ResumeCallback(action="show_result").pack(),
                )
            ]
        ]
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=back_kb)
    await callback.answer()


# ── Step 6 → 7: summary completion hook ──────────────────────────────────────


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


# ── Called by work_experience module on continue / skip ───────────────────────


async def handle_resume_work_exp_done(
    callback: CallbackQuery,
    i18n: I18nContext,
    user: User | None = None,
    state: FSMContext | None = None,
    session: AsyncSession | None = None,
) -> None:
    """Called by work_experience module when user continues from the work-exp list."""
    if user is not None and state is not None and session is not None:
        await _ensure_resume_record(state, session, user.id)

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


# ── Resume creation: initialise DB record on first real step ─────────────────


async def _ensure_resume_record(
    state: FSMContext,
    session: AsyncSession,
    user_id: int,
) -> int:
    """Create or retrieve the Resume DB record for this session; return its id."""
    from src.repositories.resume import ResumeRepository

    data = await state.get_data()
    resume_id: int | None = data.get("res_resume_id")
    if resume_id:
        return resume_id

    job_title: str = data.get("res_job_title", "")
    skill_level: str | None = data.get("res_skill_level")

    repo = ResumeRepository(session)
    resume = await repo.create(user_id=user_id, job_title=job_title, skill_level=skill_level)
    await session.commit()
    await state.update_data(res_resume_id=resume.id)
    return resume.id
