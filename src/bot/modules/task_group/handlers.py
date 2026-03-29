"""Main menu: run user task group and configure steps."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.callbacks.common import MenuCallback
from src.bot.callbacks.task_group import TaskGroupCallback
from src.core.i18n import I18nContext
from src.models.user import User
from src.repositories.autoparse import AutoparseCompanyRepository
from src.repositories.parsing import ParsingCompanyRepository
from src.services.task_group import (
    append_task_group_step,
    clear_task_group_steps,
    load_task_group_steps,
    remove_task_group_step_at,
)

router = Router(name="task_group")


def _format_steps_text(
    steps: list[dict],
    i18n: I18nContext,
) -> str:
    if not steps:
        return i18n.get("task-group-settings-empty")
    lines = [i18n.get("task-group-settings-list-title")]
    for i, s in enumerate(steps, start=1):
        kind = s.get("kind", "")
        cid = s.get("company_id", "")
        label_key = {
            "autoparse": "task-group-kind-autoparse",
            "autorespond": "task-group-kind-autorespond",
            "parsing": "task-group-kind-parsing",
        }.get(kind, "task-group-kind-unknown")
        lines.append(f"{i}. {i18n.get(label_key)} — id {cid}")
    return "\n".join(lines)


def _settings_keyboard(
    i18n: I18nContext,
    steps: list[dict],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=i18n.get("task-group-add-autoparse"),
                callback_data=TaskGroupCallback(action="add_menu", kind="autoparse").pack(),
            ),
            InlineKeyboardButton(
                text=i18n.get("task-group-add-autorespond"),
                callback_data=TaskGroupCallback(action="add_menu", kind="autorespond").pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text=i18n.get("task-group-add-parsing"),
                callback_data=TaskGroupCallback(action="add_menu", kind="parsing").pack(),
            ),
        ],
    ]
    for idx, _ in enumerate(steps):
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("task-group-remove-step", index=idx + 1),
                    callback_data=TaskGroupCallback(action="remove", index=idx).pack(),
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("task-group-clear"),
                callback_data=TaskGroupCallback(action="clear").pack(),
            ),
            InlineKeyboardButton(
                text=i18n.get("btn-back-menu"),
                callback_data=MenuCallback(action="main").pack(),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_task_group_settings(
    callback: CallbackQuery,
    user: User,
    i18n: I18nContext,
) -> None:
    if not user.telegram_id:
        return
    steps = load_task_group_steps(user.telegram_id)
    text = _format_steps_text(steps, i18n)
    await callback.message.edit_text(
        text,
        reply_markup=_settings_keyboard(i18n, steps),
    )


async def _company_pick_keyboard(
    *,
    session: AsyncSession,
    user: User,
    kind: str,
    i18n: I18nContext,
) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    if kind in ("autoparse", "autorespond"):
        repo = AutoparseCompanyRepository(session)
        companies = await repo.get_by_user(user.id, limit=100)
        for c in companies:
            label = (c.vacancy_title or f"#{c.id}")[:40]
            rows.append(
                [
                    InlineKeyboardButton(
                        text=label,
                        callback_data=TaskGroupCallback(
                            action="pick",
                            kind=kind,
                            company_id=c.id,
                        ).pack(),
                    ),
                ]
            )
    elif kind == "parsing":
        repo = ParsingCompanyRepository(session)
        companies = await repo.get_by_user(user.id, limit=100)
        for c in companies:
            title = (c.vacancy_title or c.search_url or f"#{c.id}")[:40]
            rows.append(
                [
                    InlineKeyboardButton(
                        text=title,
                        callback_data=TaskGroupCallback(
                            action="pick",
                            kind=kind,
                            company_id=c.id,
                        ).pack(),
                    ),
                ]
            )
    else:
        return None
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=TaskGroupCallback(action="back_settings").pack(),
            ),
        ]
    )
    if len(rows) == 1:
        return None
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(MenuCallback.filter(F.action == "task_group_run"))
async def handle_task_group_run(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    if not user.telegram_id:
        await callback.answer(i18n.get("access-denied"), show_alert=True)
        return
    steps = load_task_group_steps(user.telegram_id)
    if not steps:
        await callback.answer(
            i18n.get("task-group-run-empty"),
            show_alert=True,
        )
        return

    enqueued = 0
    skipped = 0
    from src.worker.tasks.autoparse import run_autoparse_company
    from src.worker.tasks.autorespond import run_autorespond_company
    from src.worker.tasks.parsing import run_parsing_company

    for step in steps:
        kind = step.get("kind")
        cid = step.get("company_id")
        if kind not in ("autoparse", "autorespond", "parsing") or not cid:
            skipped += 1
            continue
        ok = False
        if kind == "autoparse":
            repo = AutoparseCompanyRepository(session)
            co = await repo.get_by_id(int(cid))
            if co and co.user_id == user.id and not co.is_deleted:
                run_autoparse_company.delay(int(cid), notify_user_id=user.id)
                ok = True
        elif kind == "autorespond":
            repo = AutoparseCompanyRepository(session)
            co = await repo.get_by_id(int(cid))
            if co and co.user_id == user.id and not co.is_deleted:
                run_autorespond_company.delay(int(cid))
                ok = True
        elif kind == "parsing":
            repo = ParsingCompanyRepository(session)
            co = await repo.get_by_id_for_user(int(cid), user.id)
            if co:
                run_parsing_company.delay(
                    int(cid),
                    user.id,
                    include_blacklisted=False,
                    telegram_chat_id=user.telegram_id,
                )
                ok = True
        if ok:
            enqueued += 1
        else:
            skipped += 1

    await callback.answer(
        i18n.get(
            "task-group-run-done",
            enqueued=enqueued,
            skipped=skipped,
        ),
        show_alert=True,
    )


@router.callback_query(MenuCallback.filter(F.action == "task_group_settings"))
async def handle_task_group_settings_entry(
    callback: CallbackQuery,
    user: User,
    i18n: I18nContext,
) -> None:
    if not user.telegram_id:
        await callback.answer(i18n.get("access-denied"), show_alert=True)
        return
    await callback.answer()
    await _show_task_group_settings(callback, user, i18n)


@router.callback_query(TaskGroupCallback.filter(F.action == "back_settings"))
async def task_group_back_settings(
    callback: CallbackQuery,
    user: User,
    i18n: I18nContext,
) -> None:
    await callback.answer()
    await _show_task_group_settings(callback, user, i18n)


@router.callback_query(TaskGroupCallback.filter(F.action == "add_menu"))
async def task_group_add_menu(
    callback: CallbackQuery,
    callback_data: TaskGroupCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    if not user.telegram_id:
        await callback.answer(i18n.get("access-denied"), show_alert=True)
        return
    kind = callback_data.kind
    if kind not in ("autoparse", "autorespond", "parsing"):
        await callback.answer()
        return
    kb = await _company_pick_keyboard(session=session, user=user, kind=kind, i18n=i18n)
    await callback.answer()
    kind_label = {
        "autoparse": "task-group-kind-autoparse",
        "autorespond": "task-group-kind-autorespond",
        "parsing": "task-group-kind-parsing",
    }.get(kind, "task-group-kind-unknown")
    if not kb:
        await callback.message.edit_text(
            i18n.get("task-group-no-companies"),
            reply_markup=_settings_keyboard(i18n, load_task_group_steps(user.telegram_id)),
        )
        return
    await callback.message.edit_text(
        i18n.get("task-group-pick-company", kind=i18n.get(kind_label)),
        reply_markup=kb,
    )


@router.callback_query(TaskGroupCallback.filter(F.action == "pick"))
async def task_group_pick(
    callback: CallbackQuery,
    callback_data: TaskGroupCallback,
    user: User,
    i18n: I18nContext,
) -> None:
    if not user.telegram_id:
        await callback.answer(i18n.get("access-denied"), show_alert=True)
        return
    kind = callback_data.kind
    cid = callback_data.company_id
    if kind not in ("autoparse", "autorespond", "parsing") or cid <= 0:
        await callback.answer()
        return
    append_task_group_step(user.telegram_id, kind, cid)
    await callback.answer(i18n.get("task-group-step-added"))
    await _show_task_group_settings(callback, user, i18n)


@router.callback_query(TaskGroupCallback.filter(F.action == "remove"))
async def task_group_remove(
    callback: CallbackQuery,
    callback_data: TaskGroupCallback,
    user: User,
    i18n: I18nContext,
) -> None:
    if not user.telegram_id:
        await callback.answer(i18n.get("access-denied"), show_alert=True)
        return
    idx = callback_data.index
    if idx < 0:
        await callback.answer()
        return
    remove_task_group_step_at(user.telegram_id, idx)
    await callback.answer()
    await _show_task_group_settings(callback, user, i18n)


@router.callback_query(TaskGroupCallback.filter(F.action == "clear"))
async def task_group_clear(
    callback: CallbackQuery,
    user: User,
    i18n: I18nContext,
) -> None:
    if not user.telegram_id:
        await callback.answer(i18n.get("access-denied"), show_alert=True)
        return
    clear_task_group_steps(user.telegram_id)
    await callback.answer(i18n.get("task-group-cleared"))
    await _show_task_group_settings(callback, user, i18n)
