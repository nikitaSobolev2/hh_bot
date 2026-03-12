"""Shared Work Experience CRUD handlers.

All other modules that need to let users manage their work experience
should redirect here instead of duplicating the flow.

The ``return_to`` field in ``WorkExpCallback`` encodes where to navigate
when the user is done:
- ``"menu"``                 → main menu
- ``"parsing:<id>"``         → key phrases step for parsing company <id>
- ``"autoparse_settings"``   → autoparse settings hub
- ``"achievements"``         → achievement generator list
- ``"achievements_collect"`` → start achievement collection FSM
- ``"resume_step1"``         → resume build flow
"""

from __future__ import annotations

import contextlib

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.modules.parsing import services as we_service
from src.bot.modules.work_experience.callbacks import WorkExpCallback
from src.bot.modules.work_experience.keyboards import (
    MAX_WORK_EXPERIENCES,
    cancel_add_keyboard,
    cancel_edit_keyboard,
    work_exp_ai_input_keyboard,
    work_exp_detail_keyboard,
    work_exp_optional_keyboard,
    work_experience_keyboard,
)
from src.bot.modules.work_experience.states import WorkExpForm
from src.core.i18n import I18nContext
from src.models.user import User
from src.repositories.work_experience_ai_draft import WorkExperienceAiDraftRepository

router = Router(name="work_experience")

_FIELD_COMPANY_NAME = "company_name"
_FIELD_TITLE = "title"
_FIELD_PERIOD = "period"
_FIELD_STACK = "stack"
_FIELD_ACHIEVEMENTS = "achievements"
_FIELD_DUTIES = "duties"


# ── Public display helpers ────────────────────────────────────────────────────


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
    disabled_exp_ids: set[int] | None = None,
) -> None:
    experiences = await we_service.get_active_work_experiences(session, user.id)

    text = f"<b>{i18n.get('work-exp-title')}</b>\n\n{i18n.get('work-exp-prompt')}"

    kb = work_experience_keyboard(
        experiences,
        return_to,
        i18n,
        show_continue=show_continue,
        show_skip=show_skip,
        disabled_exp_ids=disabled_exp_ids or set(),
    )
    if edit:
        with contextlib.suppress(TelegramBadRequest):
            await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


async def show_work_exp_detail(
    message,
    work_exp_id: int,
    return_to: str,
    session: AsyncSession,
    i18n: I18nContext,
    *,
    edit: bool = True,
    disabled_exp_ids: set[int] | None = None,
) -> None:
    from src.repositories.work_experience import WorkExperienceRepository

    repo = WorkExperienceRepository(session)
    exp = await repo.get_by_id(work_exp_id)
    if not exp or not exp.is_active:
        with contextlib.suppress(TelegramBadRequest):
            await message.edit_text(i18n.get("work-exp-not-found"))
        return

    in_resume_context = return_to.startswith("resume")
    is_disabled = work_exp_id in (disabled_exp_ids or set())

    text = _format_detail_text(exp, i18n)
    kb = work_exp_detail_keyboard(
        work_exp_id,
        return_to,
        i18n,
        show_resume_toggle=in_resume_context,
        is_disabled=is_disabled,
    )
    if edit:
        with contextlib.suppress(TelegramBadRequest):
            await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


def _format_detail_text(exp, i18n: I18nContext) -> str:
    lines = [f"<b>🏢 {exp.company_name}</b>"]
    if exp.title:
        lines.append(f"📋 {exp.title}")
    if exp.period:
        lines.append(f"📅 {exp.period}")
    lines.append(f"🛠 {exp.stack}")
    lines.append("")
    ach_val = exp.achievements or f"<i>{i18n.get('we-not-set')}</i>"
    duties_val = exp.duties or f"<i>{i18n.get('we-not-set')}</i>"
    lines.append(f"🏆 <b>{i18n.get('we-label-achievements')}</b>\n{ach_val}")
    lines.append("")
    lines.append(f"🔧 <b>{i18n.get('we-label-duties')}</b>\n{duties_val}")
    return "\n".join(lines)


# ── List view ────────────────────────────────────────────────────────────────


@router.callback_query(WorkExpCallback.filter(F.action == "view"))
async def handle_view(
    callback: CallbackQuery,
    callback_data: WorkExpCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    return_to = callback_data.return_to
    in_resume_context = return_to.startswith("resume")
    disabled_ids: set[int] = set()
    if in_resume_context:
        data = await state.get_data()
        disabled_ids = set(data.get("res_disabled_exp_ids") or [])
    await show_work_experience(
        callback.message,
        user,
        return_to,
        session,
        i18n,
        show_continue=in_resume_context,
        show_skip=in_resume_context,
        disabled_exp_ids=disabled_ids,
    )
    await callback.answer()


# ── Detail view ──────────────────────────────────────────────────────────────


@router.callback_query(WorkExpCallback.filter(F.action == "detail"))
async def handle_detail(
    callback: CallbackQuery,
    callback_data: WorkExpCallback,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    disabled_ids: set[int] = set()
    if callback_data.return_to.startswith("resume"):
        data = await state.get_data()
        disabled_ids = set(data.get("res_disabled_exp_ids") or [])
    await show_work_exp_detail(
        callback.message,
        callback_data.work_exp_id,
        callback_data.return_to,
        session,
        i18n,
        disabled_exp_ids=disabled_ids,
    )
    await callback.answer()


@router.callback_query(WorkExpCallback.filter(F.action == "toggle_for_resume"))
async def handle_toggle_for_resume(
    callback: CallbackQuery,
    callback_data: WorkExpCallback,
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
    disabled_ids = set(disabled)
    await show_work_exp_detail(
        callback.message,
        exp_id,
        callback_data.return_to,
        session,
        i18n,
        disabled_exp_ids=disabled_ids,
    )
    await callback.answer()


@router.callback_query(WorkExpCallback.filter(F.action == "delete"))
async def handle_delete(
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
    await callback.answer(i18n.get("we-deleted"))


# ── Creation FSM ─────────────────────────────────────────────────────────────


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
    await state.set_state(WorkExpForm.title)
    await message.answer(
        i18n.get("work-exp-enter-title"),
        reply_markup=work_exp_optional_keyboard(data["we_return_to"], _FIELD_TITLE, i18n),
    )


@router.message(WorkExpForm.title)
async def fsm_title(
    message: Message,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    text = (message.text or "").strip() or None
    if text and len(text) > 255:
        await message.answer(i18n.get("work-exp-title-invalid"))
        return
    await state.update_data(we_title=text)
    await _ask_for_period(message, state, i18n)


@router.message(WorkExpForm.period)
async def fsm_period(
    message: Message,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    text = (message.text or "").strip() or None
    await state.update_data(we_period=text)
    await _ask_for_stack(message, state, i18n)


@router.message(WorkExpForm.stack)
async def fsm_stack(
    message: Message,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    stack = (message.text or "").strip()
    if not stack:
        await message.answer(i18n.get("work-exp-stack-invalid"))
        return

    data = await state.get_data()
    return_to = data["we_return_to"]
    company_name = data["we_company_name"]

    await state.update_data(we_stack=stack)
    await state.set_state(WorkExpForm.achievements)
    await message.answer(
        i18n.get("work-exp-enter-achievements", company=company_name),
        reply_markup=work_exp_ai_input_keyboard(return_to, _FIELD_ACHIEVEMENTS, i18n),
    )


@router.message(WorkExpForm.achievements)
async def fsm_achievements(
    message: Message,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    text = (message.text or "").strip() or None
    await state.update_data(we_achievements=text)
    await _ask_for_duties(message, state, i18n)


@router.message(WorkExpForm.duties)
async def fsm_duties(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    text = (message.text or "").strip() or None
    await state.update_data(we_duties=text)
    await _finish_work_experience_creation(message, user, state, session, i18n)


@router.callback_query(
    WorkExpCallback.filter(F.action == "generate_ai"),
    StateFilter(WorkExpForm.achievements, WorkExpForm.duties),
)
async def handle_generate_ai(
    callback: CallbackQuery,
    callback_data: WorkExpCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    from src.worker.tasks.work_experience import generate_work_experience_ai_task

    data = await state.get_data()
    company_name: str = data.get("we_company_name", "")
    title: str | None = data.get("we_title")
    stack: str = data.get("we_stack", "")
    field = callback_data.field

    await callback.answer()

    wait_msg = None
    with contextlib.suppress(TelegramBadRequest):
        wait_msg = await callback.message.edit_text(i18n.get("work-exp-generating"))

    generate_work_experience_ai_task.delay(
        user_id=user.id,
        chat_id=callback.message.chat.id,
        message_id=wait_msg.message_id if wait_msg else callback.message.message_id,
        field=field,
        mode="create",
        locale=user.language_code or "ru",
        company_name=company_name,
        title=title,
        stack=stack,
        period=data.get("we_period"),
        return_to=callback_data.return_to,
    )


@router.callback_query(
    WorkExpCallback.filter(F.action == "accept_draft"),
    StateFilter(WorkExpForm.achievements, WorkExpForm.duties),
)
async def handle_accept_draft(
    callback: CallbackQuery,
    callback_data: WorkExpCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    draft_repo = WorkExperienceAiDraftRepository(session)
    draft = await draft_repo.get(user.id, callback_data.field)
    text: str | None = draft.generated_text if draft else None
    if draft:
        await draft_repo.delete(user.id, callback_data.field)
        await session.commit()

    data = await state.get_data()
    company_name: str = data.get("we_company_name", "")

    await callback.answer()

    if callback_data.field == _FIELD_ACHIEVEMENTS:
        await state.update_data(we_achievements=text)
        await state.set_state(WorkExpForm.duties)
        await callback.message.answer(
            i18n.get(
                "work-exp-generated-achievements",
                text=text or i18n.get("work-exp-generation-failed"),
            )
        )
        await callback.message.answer(
            i18n.get("work-exp-enter-duties", company=company_name),
            reply_markup=work_exp_ai_input_keyboard(callback_data.return_to, _FIELD_DUTIES, i18n),
        )
    else:
        await state.update_data(we_duties=text)
        await _finish_work_experience_creation(callback.message, user, state, session, i18n)


@router.callback_query(
    WorkExpCallback.filter(F.action == "skip_field"),
    StateFilter(
        WorkExpForm.title,
        WorkExpForm.period,
        WorkExpForm.achievements,
        WorkExpForm.duties,
    ),
)
async def handle_skip_field(
    callback: CallbackQuery,
    callback_data: WorkExpCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    company_name: str = data.get("we_company_name", "")
    field = callback_data.field

    if field == _FIELD_TITLE:
        await state.update_data(we_title=None)
        await _ask_for_period(callback.message, state, i18n, edit=True)

    elif field == _FIELD_PERIOD:
        await state.update_data(we_period=None)
        await _ask_for_stack(callback.message, state, i18n, edit=True)

    elif field == _FIELD_ACHIEVEMENTS:
        await state.update_data(we_achievements=None)
        await state.set_state(WorkExpForm.duties)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("work-exp-enter-duties", company=company_name),
                reply_markup=work_exp_ai_input_keyboard(
                    callback_data.return_to, _FIELD_DUTIES, i18n
                ),
            )
    else:
        await state.update_data(we_duties=None)
        await _finish_work_experience_creation(callback.message, user, state, session, i18n)

    await callback.answer()


async def _ask_for_period(
    message: Message,
    state: FSMContext,
    i18n: I18nContext,
    *,
    edit: bool = False,
) -> None:
    data = await state.get_data()
    return_to: str = data.get("we_return_to", "menu")
    await state.set_state(WorkExpForm.period)
    kb = work_exp_optional_keyboard(return_to, _FIELD_PERIOD, i18n)
    if edit:
        with contextlib.suppress(TelegramBadRequest):
            await message.edit_text(i18n.get("work-exp-enter-period"), reply_markup=kb)
    else:
        await message.answer(i18n.get("work-exp-enter-period"), reply_markup=kb)


async def _ask_for_stack(
    message: Message,
    state: FSMContext,
    i18n: I18nContext,
    *,
    edit: bool = False,
) -> None:
    data = await state.get_data()
    return_to: str = data.get("we_return_to", "menu")
    company_name: str = data.get("we_company_name", "")
    await state.set_state(WorkExpForm.stack)
    kb = cancel_add_keyboard(return_to, i18n)
    if edit:
        with contextlib.suppress(TelegramBadRequest):
            await message.edit_text(
                i18n.get("work-exp-enter-stack", company=company_name), reply_markup=kb
            )
    else:
        await message.answer(
            i18n.get("work-exp-enter-stack", company=company_name), reply_markup=kb
        )


async def _ask_for_duties(
    message: Message,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    company_name: str = data.get("we_company_name", "")
    return_to: str = data.get("we_return_to", "menu")
    await state.set_state(WorkExpForm.duties)
    await message.answer(
        i18n.get("work-exp-enter-duties", company=company_name),
        reply_markup=work_exp_ai_input_keyboard(return_to, _FIELD_DUTIES, i18n),
    )


async def _finish_work_experience_creation(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    return_to: str = data["we_return_to"]
    company_name: str = data["we_company_name"]
    title: str | None = data.get("we_title")
    period: str | None = data.get("we_period")
    stack: str = data["we_stack"]
    achievements: str | None = data.get("we_achievements")
    duties: str | None = data.get("we_duties")
    await state.clear()

    await we_service.add_work_experience(
        session,
        user.id,
        company_name,
        stack,
        title=title,
        period=period,
        achievements=achievements,
        duties=duties,
    )
    await show_work_experience(message, user, return_to, session, i18n, edit=False)


# ── Cancel add ───────────────────────────────────────────────────────────────


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


# ── Edit FSM ──────────────────────────────────────────────────────────────────


@router.callback_query(WorkExpCallback.filter(F.action == "edit_field"))
async def handle_edit_field(
    callback: CallbackQuery,
    callback_data: WorkExpCallback,
    user: User,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    field = callback_data.field
    work_exp_id = callback_data.work_exp_id
    return_to = callback_data.return_to

    await state.clear()
    await state.update_data(
        we_editing_id=work_exp_id,
        we_editing_field=field,
        we_return_to=return_to,
    )

    prompt_key = _field_prompt_key(field)
    cancel_kb = cancel_edit_keyboard(work_exp_id, return_to, i18n)

    if field in (_FIELD_ACHIEVEMENTS, _FIELD_DUTIES):
        await state.set_state(
            WorkExpForm.edit_achievements
            if field == _FIELD_ACHIEVEMENTS
            else WorkExpForm.edit_duties
        )
        ai_kb = work_exp_ai_input_keyboard(return_to, field, i18n)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(i18n.get(prompt_key), reply_markup=ai_kb)
    else:
        await state.set_state(WorkExpForm.edit_value)
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(i18n.get(prompt_key), reply_markup=cancel_kb)

    await callback.answer()


@router.message(WorkExpForm.edit_value)
async def fsm_edit_value(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    work_exp_id: int = data["we_editing_id"]
    field: str = data["we_editing_field"]
    return_to: str = data["we_return_to"]

    new_value = (message.text or "").strip() or None

    if field == _FIELD_COMPANY_NAME and (not new_value or len(new_value) > 255):
        await message.answer(i18n.get("work-exp-name-invalid"))
        return
    if field == _FIELD_STACK and not new_value:
        await message.answer(i18n.get("work-exp-stack-invalid"))
        return

    await _save_field(session, user.id, work_exp_id, field, new_value)
    await state.clear()
    await show_work_exp_detail(message, work_exp_id, return_to, session, i18n, edit=False)


@router.message(WorkExpForm.edit_achievements)
async def fsm_edit_achievements(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    work_exp_id: int = data["we_editing_id"]
    return_to: str = data["we_return_to"]
    new_value = (message.text or "").strip() or None
    await _save_field(session, user.id, work_exp_id, _FIELD_ACHIEVEMENTS, new_value)
    await state.clear()
    await show_work_exp_detail(message, work_exp_id, return_to, session, i18n, edit=False)


@router.message(WorkExpForm.edit_duties)
async def fsm_edit_duties(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    work_exp_id: int = data["we_editing_id"]
    return_to: str = data["we_return_to"]
    new_value = (message.text or "").strip() or None
    await _save_field(session, user.id, work_exp_id, _FIELD_DUTIES, new_value)
    await state.clear()
    await show_work_exp_detail(message, work_exp_id, return_to, session, i18n, edit=False)


@router.callback_query(
    WorkExpCallback.filter(F.action == "generate_ai"), WorkExpForm.edit_achievements
)
async def handle_edit_generate_ai_achievements(
    callback: CallbackQuery,
    callback_data: WorkExpCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await _handle_edit_generate_ai(
        callback, callback_data, user, state, session, i18n, _FIELD_ACHIEVEMENTS
    )


@router.callback_query(WorkExpCallback.filter(F.action == "generate_ai"), WorkExpForm.edit_duties)
async def handle_edit_generate_ai_duties(
    callback: CallbackQuery,
    callback_data: WorkExpCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await _handle_edit_generate_ai(
        callback, callback_data, user, state, session, i18n, _FIELD_DUTIES
    )


async def _handle_edit_generate_ai(
    callback: CallbackQuery,
    callback_data: WorkExpCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
    field: str,
) -> None:
    from src.repositories.work_experience import WorkExperienceRepository

    data = await state.get_data()
    work_exp_id: int = data["we_editing_id"]
    return_to: str = data["we_return_to"]

    from src.worker.tasks.work_experience import generate_work_experience_ai_task

    repo = WorkExperienceRepository(session)
    exp = await repo.get_by_id(work_exp_id)
    if not exp:
        await callback.answer(i18n.get("work-exp-not-found"), show_alert=True)
        return

    await callback.answer()
    await state.clear()

    wait_msg = None
    with contextlib.suppress(TelegramBadRequest):
        wait_msg = await callback.message.edit_text(i18n.get("work-exp-generating"))

    generate_work_experience_ai_task.delay(
        user_id=user.id,
        chat_id=callback.message.chat.id,
        message_id=wait_msg.message_id if wait_msg else callback.message.message_id,
        field=field,
        mode="edit",
        locale=user.language_code or "ru",
        work_exp_id=work_exp_id,
        return_to=return_to,
    )


@router.callback_query(
    WorkExpCallback.filter(F.action == "skip_field"), WorkExpForm.edit_achievements
)
async def handle_edit_skip_achievements(
    callback: CallbackQuery,
    callback_data: WorkExpCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    work_exp_id: int = data["we_editing_id"]
    return_to: str = data["we_return_to"]
    await state.clear()
    await show_work_exp_detail(callback.message, work_exp_id, return_to, session, i18n)
    await callback.answer()


@router.callback_query(WorkExpCallback.filter(F.action == "skip_field"), WorkExpForm.edit_duties)
async def handle_edit_skip_duties(
    callback: CallbackQuery,
    callback_data: WorkExpCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    work_exp_id: int = data["we_editing_id"]
    return_to: str = data["we_return_to"]
    await state.clear()
    await show_work_exp_detail(callback.message, work_exp_id, return_to, session, i18n)
    await callback.answer()


async def _save_field(
    session: AsyncSession,
    user_id: int,
    work_exp_id: int,
    field: str,
    value: str | None,
) -> None:
    from src.repositories.work_experience import WorkExperienceRepository

    repo = WorkExperienceRepository(session)
    exp = await repo.get_by_id(work_exp_id)
    if exp and exp.user_id == user_id:
        await repo.update(exp, **{field: value})
        await session.commit()


def _field_prompt_key(field: str) -> str:
    mapping = {
        _FIELD_COMPANY_NAME: "work-exp-enter-name",
        _FIELD_TITLE: "work-exp-enter-title",
        _FIELD_PERIOD: "work-exp-enter-period",
        _FIELD_STACK: "we-edit-enter-stack",
        _FIELD_ACHIEVEMENTS: "work-exp-enter-achievements-edit",
        _FIELD_DUTIES: "work-exp-enter-duties-edit",
    }
    return mapping.get(field, "work-exp-enter-name")


# ── Navigation ────────────────────────────────────────────────────────────────


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
    await _navigate_return_to(callback, user, session, i18n, callback_data.return_to, state=state)
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
    await _navigate_return_to(callback, user, session, i18n, callback_data.return_to, state=state)
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
    await _navigate_return_to(callback, user, session, i18n, callback_data.return_to, state=state)
    await callback.answer()


async def _navigate_return_to(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
    return_to: str,
    *,
    state: FSMContext | None = None,
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

    elif return_to == "achievements_collect":
        from src.bot.modules.achievements.handlers import start_achievement_collection

        await start_achievement_collection(callback, user, session, state, i18n)

    elif return_to == "resume_step1":
        from src.bot.modules.resume.handlers import handle_resume_work_exp_done

        await handle_resume_work_exp_done(callback, i18n, user=user, state=state, session=session)
