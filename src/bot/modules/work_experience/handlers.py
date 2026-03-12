"""Shared Work Experience CRUD handlers.

All other modules that need to let users manage their work experience
should redirect here instead of duplicating the flow.

The ``return_to`` field in ``WorkExpCallback`` encodes where to navigate
when the user is done:
- ``"menu"``              → main menu
- ``"parsing:<id>"``      → key phrases step for parsing company <id>
- ``"autoparse_settings"``→ autoparse settings hub
- ``"achievements"``      → achievement generator
"""

from __future__ import annotations

import contextlib

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.modules.parsing import services as we_service
from src.bot.modules.work_experience.callbacks import WorkExpCallback
from src.bot.modules.work_experience.keyboards import (
    MAX_WORK_EXPERIENCES,
    cancel_add_keyboard,
    work_experience_keyboard,
)
from src.bot.modules.work_experience.states import WorkExpForm
from src.core.i18n import I18nContext
from src.models.user import User

router = Router(name="work_experience")


async def show_work_experience(
    message,
    user: User,
    return_to: str,
    session: AsyncSession,
    i18n: I18nContext,
    *,
    edit: bool = True,
    show_continue: bool = False,
    show_skip: bool = False,
) -> None:
    experiences = await we_service.get_active_work_experiences(session, user.id)

    title_key = "work-exp-title"
    text = f"<b>{i18n.get(title_key)}</b>\n\n{i18n.get('work-exp-prompt')}"
    if experiences:
        lines = [f"  \u2022 <b>{e.company_name}</b> \u2014 {e.stack}" for e in experiences]
        text += "\n\n" + "\n".join(lines)

    kb = work_experience_keyboard(
        experiences,
        return_to,
        i18n,
        show_continue=show_continue,
        show_skip=show_skip,
    )
    if edit:
        with contextlib.suppress(TelegramBadRequest):
            await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


@router.callback_query(WorkExpCallback.filter(F.action == "view"))
async def handle_view(
    callback: CallbackQuery,
    callback_data: WorkExpCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await show_work_experience(
        callback.message,
        user,
        callback_data.return_to,
        session,
        i18n,
    )
    await callback.answer()


@router.callback_query(WorkExpCallback.filter(F.action == "add"))
async def handle_add(
    callback: CallbackQuery,
    callback_data: WorkExpCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    active_count = await we_service.count_active_work_experiences(session, user.id)
    if active_count >= MAX_WORK_EXPERIENCES:
        await callback.answer(i18n.get("work-exp-max-reached"), show_alert=True)
        return

    await state.set_state(WorkExpForm.company_name)
    await state.update_data(we_return_to=callback_data.return_to)
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            i18n.get("work-exp-enter-name"),
            reply_markup=cancel_add_keyboard(callback_data.return_to, i18n),
        )
    await callback.answer()


@router.message(WorkExpForm.company_name)
async def fsm_company_name(
    message: Message,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    name = (message.text or "").strip()
    if not name or len(name) > 255:
        await message.answer(i18n.get("work-exp-name-invalid"))
        return

    data = await state.get_data()
    await state.update_data(we_company_name=name)
    await state.set_state(WorkExpForm.stack)
    await message.answer(
        i18n.get("work-exp-enter-stack", company=name),
        reply_markup=cancel_add_keyboard(data["we_return_to"], i18n),
    )


@router.message(WorkExpForm.stack)
async def fsm_stack(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    stack = (message.text or "").strip()
    if not stack:
        await message.answer(i18n.get("work-exp-stack-invalid"))
        return

    data = await state.get_data()
    return_to = data["we_return_to"]
    company_name = data["we_company_name"]
    await state.clear()

    await we_service.add_work_experience(session, user.id, company_name, stack)
    await show_work_experience(message, user, return_to, session, i18n, edit=False)


@router.callback_query(WorkExpCallback.filter(F.action == "cancel_add"))
async def handle_cancel_add(
    callback: CallbackQuery,
    callback_data: WorkExpCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await state.clear()
    await show_work_experience(callback.message, user, callback_data.return_to, session, i18n)
    await callback.answer()


@router.callback_query(WorkExpCallback.filter(F.action == "remove"))
async def handle_remove(
    callback: CallbackQuery,
    callback_data: WorkExpCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    deactivated = await we_service.deactivate_work_experience(
        session, callback_data.work_exp_id, user.id
    )
    if not deactivated:
        await callback.answer(i18n.get("parsing-not-found"), show_alert=True)
        return
    await show_work_experience(callback.message, user, callback_data.return_to, session, i18n)
    await callback.answer()


@router.callback_query(WorkExpCallback.filter(F.action == "back"))
async def handle_back(
    callback: CallbackQuery,
    callback_data: WorkExpCallback,
    user: User,
    session: AsyncSession,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.clear()
    await _navigate_return_to(callback, user, session, i18n, callback_data.return_to)
    await callback.answer()


@router.callback_query(WorkExpCallback.filter(F.action == "skip"))
async def handle_skip(
    callback: CallbackQuery,
    callback_data: WorkExpCallback,
    user: User,
    session: AsyncSession,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await _navigate_return_to(callback, user, session, i18n, callback_data.return_to)
    await callback.answer()


@router.callback_query(WorkExpCallback.filter(F.action == "continue"))
async def handle_continue(
    callback: CallbackQuery,
    callback_data: WorkExpCallback,
    user: User,
    session: AsyncSession,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await _navigate_return_to(callback, user, session, i18n, callback_data.return_to)
    await callback.answer()


async def _navigate_return_to(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
    return_to: str,
) -> None:
    if return_to == "menu":
        from src.bot.keyboards.common import main_menu_admin_keyboard, main_menu_keyboard

        kb = main_menu_admin_keyboard(i18n) if user.is_admin else main_menu_keyboard(i18n)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(i18n.get("welcome"), reply_markup=kb)

    elif return_to.startswith("parsing:"):
        company_id = int(return_to.split(":")[1])
        from src.bot.modules.parsing.handlers import _show_work_experience_step

        await _show_work_experience_step(
            callback.message, user, company_id, session, i18n, edit=True
        )

    elif return_to == "autoparse_settings":
        from src.bot.modules.autoparse.handlers import settings_hub

        await settings_hub(callback, user, session, i18n)

    elif return_to == "achievements":
        from src.bot.modules.achievements.handlers import show_achievement_list

        await show_achievement_list(callback, user, session, i18n)

    elif return_to == "resume_step1":
        from src.bot.modules.resume.handlers import handle_resume_work_exp_done

        await handle_resume_work_exp_done(callback, i18n)
