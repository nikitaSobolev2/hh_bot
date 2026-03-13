"""Handlers for the Achievement Generator module."""

from __future__ import annotations

import contextlib

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.modules.achievements.callbacks import AchievementCallback
from src.bot.modules.achievements.keyboards import (
    achievement_detail_keyboard,
    achievement_input_keyboard,
    achievement_list_keyboard,
    achievement_proceed_keyboard,
)
from src.bot.modules.achievements.states import AchievementForm
from src.core.i18n import I18nContext
from src.models.achievement import AchievementGeneration
from src.models.user import User
from src.repositories.achievement import AchievementGenerationRepository, AchievementItemRepository

router = Router(name="achievements")

_STEP_ACH = "achievements"
_STEP_RESP = "responsibilities"


async def show_achievement_list(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
    page: int = 0,
) -> None:
    repo = AchievementGenerationRepository(session)
    generations, total = await repo.get_by_user_paginated(user.id, page)

    text = (
        f"<b>{i18n.get('ach-list-empty')}</b>"
        if not generations and page == 0
        else f"<b>{i18n.get('ach-list-title')}</b>"
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=achievement_list_keyboard(generations, page, total, i18n),
        )


@router.callback_query(AchievementCallback.filter(F.action == "list"))
async def handle_list(
    callback: CallbackQuery,
    callback_data: AchievementCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await show_achievement_list(callback, user, session, i18n, callback_data.page)
    await callback.answer()


@router.callback_query(AchievementCallback.filter(F.action == "generate_new"))
async def handle_generate_new(
    callback: CallbackQuery,
    callback_data: AchievementCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.bot.modules.parsing import services as we_service
    from src.bot.modules.work_experience.handlers import show_work_experience

    experiences = await we_service.get_active_work_experiences(session, user.id)
    if not experiences:
        await show_work_experience(callback.message, user, "achievements", session, i18n)
        await callback.answer()
        return

    await show_work_experience(
        callback.message,
        user,
        "achievements_collect",
        session,
        i18n,
        show_continue=True,
    )
    await callback.answer()


async def start_achievement_collection(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    state: FSMContext | None,
    i18n: I18nContext,
) -> None:
    from src.bot.modules.parsing import services as we_service

    if state is None:
        return

    experiences = await we_service.get_active_work_experiences(session, user.id)
    if not experiences:
        from src.bot.modules.work_experience.handlers import show_work_experience

        await show_work_experience(callback.message, user, "achievements", session, i18n)
        return

    await state.clear()
    await state.update_data(
        ach_exp_ids=[exp.id for exp in experiences],
        ach_exp_names=[exp.company_name for exp in experiences],
        ach_stacks=[exp.stack for exp in experiences],
        ach_step=_STEP_ACH,
        ach_index=0,
        ach_achievements=[exp.achievements or None for exp in experiences],
        ach_responsibilities=[exp.duties or None for exp in experiences],
    )
    await state.set_state(AchievementForm.collecting_achievements)
    data = await state.get_data()
    await _ask_for_input(callback.message, data, _STEP_ACH, 0, i18n, edit=True)


async def _ask_for_input(
    message: Message,
    data: dict,
    step: str,
    index: int,
    i18n: I18nContext,
    *,
    edit: bool = False,
) -> None:
    exp_names: list[str] = data["ach_exp_names"]
    total = len(exp_names)
    company_name = exp_names[index]

    if step == _STEP_ACH:
        existing = (
            (data.get("ach_achievements") or [])[index]
            if index < len(data.get("ach_achievements") or [])
            else None
        )
        text = i18n.get(
            "ach-enter-achievements",
            company=company_name,
            current=index + 1,
            total=total,
        )
        if existing:
            text += f"\n\n<b>{i18n.get('ach-current-value')}</b>\n{existing}"
    else:
        existing = (
            (data.get("ach_responsibilities") or [])[index]
            if index < len(data.get("ach_responsibilities") or [])
            else None
        )
        text = i18n.get(
            "ach-enter-responsibilities",
            company=company_name,
            current=index + 1,
            total=total,
        )
        if existing:
            text += f"\n\n<b>{i18n.get('ach-current-value')}</b>\n{existing}"

    kb = achievement_input_keyboard(company_name, index, total, i18n)
    if edit:
        with contextlib.suppress(TelegramBadRequest):
            await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


@router.message(AchievementForm.collecting_achievements)
async def fsm_collect_achievements(
    message: Message,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    index: int = data["ach_index"]
    achievements: list = list(data["ach_achievements"])
    achievements[index] = (message.text or "").strip() or None
    await state.update_data(ach_achievements=achievements)
    await _advance_achievements_step(message, state, data, index, i18n)


@router.callback_query(
    AchievementCallback.filter(F.action == "skip_input"),
    AchievementForm.collecting_achievements,
)
async def handle_skip_achievements(
    callback: CallbackQuery,
    callback_data: AchievementCallback,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    index: int = data["ach_index"]
    await _advance_achievements_step(callback.message, state, data, index, i18n, edit=True)
    await callback.answer()


@router.callback_query(
    AchievementCallback.filter(F.action == "skip_input"),
    AchievementForm.collecting_responsibilities,
)
async def handle_skip_responsibilities(
    callback: CallbackQuery,
    callback_data: AchievementCallback,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    index: int = data["ach_index"]
    await _advance_responsibilities_step(callback.message, state, data, index, i18n, edit=True)
    await callback.answer()


async def _advance_achievements_step(
    message: Message,
    state: FSMContext,
    data: dict,
    current_index: int,
    i18n: I18nContext,
    *,
    edit: bool = False,
) -> None:
    exp_names: list[str] = data["ach_exp_names"]
    total = len(exp_names)
    next_index = current_index + 1

    if next_index < total:
        await state.update_data(ach_index=next_index)
        updated_data = {**data, "ach_index": next_index}
        await _ask_for_input(message, updated_data, _STEP_ACH, next_index, i18n, edit=edit)
        return

    await state.update_data(ach_index=0, ach_step=_STEP_RESP)
    await state.set_state(AchievementForm.collecting_responsibilities)
    fresh_data = await state.get_data()
    await _ask_for_input(message, fresh_data, _STEP_RESP, 0, i18n, edit=edit)


@router.message(AchievementForm.collecting_responsibilities)
async def fsm_collect_responsibilities(
    message: Message,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    index: int = data["ach_index"]
    responsibilities: list = list(data["ach_responsibilities"])
    responsibilities[index] = (message.text or "").strip() or None
    await state.update_data(ach_responsibilities=responsibilities)
    await _advance_responsibilities_step(message, state, data, index, i18n)


async def _advance_responsibilities_step(
    message: Message,
    state: FSMContext,
    data: dict,
    current_index: int,
    i18n: I18nContext,
    *,
    edit: bool = False,
) -> None:
    exp_names: list[str] = data["ach_exp_names"]
    total = len(exp_names)
    next_index = current_index + 1

    if next_index < total:
        await state.update_data(ach_index=next_index)
        updated_data = {**data, "ach_index": next_index}
        await _ask_for_input(message, updated_data, _STEP_RESP, next_index, i18n, edit=edit)
        return

    await _show_proceed(message, state, i18n)


async def _show_proceed(
    message: Message,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    exp_names: list[str] = data["ach_exp_names"]
    lines = [f"<b>{i18n.get('ach-proceed-title')}</b>"]
    for idx, name in enumerate(exp_names):
        ach = data["ach_achievements"][idx]
        resp = data["ach_responsibilities"][idx]
        status_parts = []
        if ach:
            status_parts.append(i18n.get("ach-has-achievements"))
        if resp:
            status_parts.append(i18n.get("ach-has-responsibilities"))
        status = ", ".join(status_parts) if status_parts else i18n.get("ach-no-input")
        lines.append(f"  • <b>{name}</b>: {status}")

    await message.answer("\n".join(lines), reply_markup=achievement_proceed_keyboard(i18n))


@router.callback_query(AchievementCallback.filter(F.action == "proceed"))
async def handle_proceed(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.worker.tasks.achievements import generate_achievements_task

    await callback.answer()

    data = await state.get_data()
    await state.clear()

    gen_repo = AchievementGenerationRepository(session)
    generation = await gen_repo.create(user.id)

    items_data = [
        {
            "work_experience_id": data["ach_exp_ids"][idx],
            "company_name": data["ach_exp_names"][idx],
            "user_achievements_input": data["ach_achievements"][idx],
            "user_responsibilities_input": data["ach_responsibilities"][idx],
        }
        for idx in range(len(data["ach_exp_names"]))
    ]

    item_repo = AchievementItemRepository(session)
    await item_repo.create_bulk(generation.id, items_data)
    await session.commit()

    wait_msg = await callback.message.edit_text(i18n.get("ach-generating"))

    from src.core.celery_async import run_celery_task

    await run_celery_task(
        generate_achievements_task,
        generation.id,
        callback.message.chat.id,
        wait_msg.message_id if wait_msg else callback.message.message_id,
        user.language_code or "ru",
    )


@router.callback_query(AchievementCallback.filter(F.action == "cancel"))
async def handle_cancel(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await state.clear()
    await show_achievement_list(callback, user, session, i18n)
    await callback.answer()


@router.callback_query(AchievementCallback.filter(F.action == "detail"))
async def handle_detail(
    callback: CallbackQuery,
    callback_data: AchievementCallback,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    repo = AchievementGenerationRepository(session)
    generation = await repo.get_by_id(callback_data.generation_id)
    if not generation or generation.is_deleted:
        await callback.answer(i18n.get("ach-not-found"), show_alert=True)
        return

    text = _format_generation(generation, i18n)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=achievement_detail_keyboard(generation.id, i18n),
        )
    await callback.answer()


def _format_generation(generation: AchievementGeneration, i18n: I18nContext) -> str:
    lines = [f"<b>{i18n.get('ach-detail-title')}</b>", ""]
    for item in generation.items:
        lines.append(f"<b>{item.company_name}</b>")
        if item.generated_text:
            lines.append(item.generated_text)
        else:
            lines.append(i18n.get("ach-no-generated-text"))
        lines.append("")
    return "\n".join(lines).strip()


@router.callback_query(AchievementCallback.filter(F.action == "delete"))
async def handle_delete(
    callback: CallbackQuery,
    callback_data: AchievementCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    repo = AchievementGenerationRepository(session)
    generation = await repo.get_by_id(callback_data.generation_id)
    if generation and generation.user_id == user.id:
        await repo.soft_delete(generation)
        await session.commit()
    await show_achievement_list(callback, user, session, i18n)
    await callback.answer(i18n.get("ach-deleted"))
