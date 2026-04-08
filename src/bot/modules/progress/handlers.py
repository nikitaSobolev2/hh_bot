"""Handlers for progress bar actions (cancel, title noop, try refresh)."""

from __future__ import annotations

import json

from aiogram import F, Router
from aiogram.filters import or_f
from aiogram.types import CallbackQuery

from src.core.celery_async import (
    normalize_celery_task_id,
    run_celery_task,
    run_sync_in_thread,
)
from src.core.i18n import I18nContext
from src.db.engine import async_session_factory
from src.models.user import User
from src.services.autorespond_progress import (
    build_hh_ui_resume_envelope_fallback_async,
    clear_autorespond_done_counter,
    clear_autorespond_failed_counter,
    clear_autorespond_ui_tail_sync,
    clear_hh_ui_batch_active_sync,
    clear_hh_ui_batch_checkpoint_sync,
    clear_hh_ui_resume_envelope_sync,
    get_hh_ui_batch_active_sync,
    is_autorespond_cancelled_sync,
    load_autorespond_ui_tail_sync,
    load_hh_ui_batch_checkpoint_full_sync,
    load_hh_ui_resume_envelope_sync,
    set_autorespond_cancelled,
)
from src.services.celery_active import celery_task_id_is_active
from src.services.progress_cancel import set_user_cancelled_sync
from src.services.progress_service import (
    PROGRESS_CANCEL_PREFIX,
    PROGRESS_CANCEL_SHORT_PREFIX,
    PROGRESS_REFRESH_PREFIX,
    PROGRESS_REFRESH_SHORT_PREFIX,
    PROGRESS_TITLE_PREFIX,
    PROGRESS_TITLE_SHORT_PREFIX,
    ProgressService,
    create_progress_redis,
    short_callback_storage_key,
)
from src.worker.app import celery_app

router = Router(name="progress")


def _parse_task_key_from_prefix(data: str, prefix: str) -> str | None:
    if not data or not data.startswith(prefix):
        return None
    encoded = data[len(prefix) :]
    return encoded.replace("_", ":") if encoded else None


async def _parse_task_key_for_progress_callback(
    redis,
    chat_id: int,
    data: str,
    *,
    long_prefix: str,
    short_prefix: str,
) -> str | None:
    """Resolve full ``task_key`` from long-form or short-token callback_data."""
    if data.startswith(short_prefix):
        token = data[len(short_prefix) :]
        if len(token) != 16:
            return None
        return await redis.get(short_callback_storage_key(chat_id, token))
    return _parse_task_key_from_prefix(data, long_prefix)


@router.callback_query(
    or_f(F.data.startswith(PROGRESS_TITLE_PREFIX), F.data.startswith(PROGRESS_TITLE_SHORT_PREFIX))
)
async def handle_progress_title(
    callback: CallbackQuery,
    user: User,
    i18n: I18nContext,
) -> None:
    """No-op label button; brief acknowledgment."""
    chat_id = callback.message.chat.id if callback.message else None
    if chat_id is None or chat_id != user.telegram_id:
        await callback.answer()
        return
    await callback.answer(
        i18n.get("progress-refresh-title-hint"),
        show_alert=False,
    )


@router.callback_query(
    or_f(
        F.data.startswith(PROGRESS_REFRESH_PREFIX),
        F.data.startswith(PROGRESS_REFRESH_SHORT_PREFIX),
    )
)
async def handle_progress_refresh(
    callback: CallbackQuery,
    user: User,
    i18n: I18nContext,
) -> None:
    """Re-dispatch task from checkpoint when the worker is not running."""
    chat_id = callback.message.chat.id if callback.message else None
    if chat_id is None or chat_id != user.telegram_id:
        await callback.answer()
        return

    redis = create_progress_redis()
    try:
        task_key = await _parse_task_key_for_progress_callback(
            redis,
            chat_id,
            callback.data or "",
            long_prefix=PROGRESS_REFRESH_PREFIX,
            short_prefix=PROGRESS_REFRESH_SHORT_PREFIX,
        )
        if not task_key:
            await callback.answer()
            return

        svc = ProgressService(
            callback.bot,
            chat_id,
            redis,
            user.language_code or "ru",
        )

        raw = await redis.get(svc._task_key(task_key))
        if not raw:
            await callback.answer(
                i18n.get("progress-task-already-finished"),
                show_alert=True,
            )
            return

        state = json.loads(raw)
        if state.get("status") == "completed":
            await callback.answer(
                i18n.get("progress-task-already-finished"),
                show_alert=True,
            )
            return

        celery_task_id = normalize_celery_task_id(state.get("celery_task_id"))

        if task_key.startswith("parse:"):
            await _try_refresh_parse(
                callback, i18n, task_key, user, celery_task_id
            )
        elif task_key.startswith("autoparse:"):
            await _try_refresh_autoparse(
                callback, i18n, task_key, user, svc, celery_task_id
            )
        elif task_key.startswith("autorespond:"):
            await _try_refresh_autorespond(
                callback, i18n, task_key, chat_id, svc
            )
        else:
            await callback.answer(
                i18n.get("progress-refresh-unsupported"),
                show_alert=True,
            )
    finally:
        await redis.aclose()


async def _try_refresh_parse(
    callback: CallbackQuery,
    i18n: I18nContext,
    task_key: str,
    user: User,
    celery_task_id: str | None,
) -> None:
    from src.repositories.parsing import ParsingCompanyRepository
    from src.worker.tasks.parsing import run_parsing_company

    rest = task_key[len("parse:") :]
    try:
        company_id = int(rest)
    except ValueError:
        await callback.answer(
            i18n.get("progress-refresh-parse-failed"),
            show_alert=True,
        )
        return

    async with async_session_factory() as session:
        repo = ParsingCompanyRepository(session)
        company = await repo.get_by_id(company_id)
        if not company or company.user_id != user.id:
            await callback.answer(
                i18n.get("progress-refresh-parse-failed"),
                show_alert=True,
            )
            return

    if celery_task_id and celery_task_id_is_active(celery_task_id):
        await callback.answer(
            i18n.get("progress-refresh-running"),
            show_alert=True,
        )
        return

    await run_celery_task(
        run_parsing_company,
        company_id,
        company.user_id,
        include_blacklisted=False,
        telegram_chat_id=user.telegram_id,
    )
    await callback.answer(
        i18n.get("progress-refresh-restarted"),
        show_alert=True,
    )


async def _try_refresh_autoparse(
    callback: CallbackQuery,
    i18n: I18nContext,
    task_key: str,
    user: User,
    svc: ProgressService,
    celery_task_id: str | None,
) -> None:
    from src.repositories.autoparse import AutoparseCompanyRepository
    from src.worker.tasks.autoparse import run_autoparse_company

    rest = task_key[len("autoparse:") :]
    try:
        company_id = int(rest)
    except ValueError:
        await callback.answer(
            i18n.get("progress-refresh-autoparse-failed"),
            show_alert=True,
        )
        return

    async with async_session_factory() as session:
        repo = AutoparseCompanyRepository(session)
        company = await repo.get_by_id(company_id)
        if not company or company.user_id != user.id:
            await callback.answer(
                i18n.get("progress-refresh-autoparse-failed"),
                show_alert=True,
            )
            return

    if celery_task_id and celery_task_id_is_active(celery_task_id):
        await callback.answer(
            i18n.get("progress-refresh-running"),
            show_alert=True,
        )
        return

    res = await run_celery_task(
        run_autoparse_company,
        company_id,
        notify_user_id=user.id,
    )
    new_id = getattr(res, "id", None)
    if new_id:
        await svc.update_celery_task_id(task_key, str(new_id))
    await callback.answer(
        i18n.get("progress-refresh-restarted"),
        show_alert=True,
    )


async def _try_refresh_autorespond(
    callback: CallbackQuery,
    i18n: I18nContext,
    task_key: str,
    chat_id: int,
    svc: ProgressService,
) -> None:
    from src.worker.tasks.hh_ui_apply import apply_to_vacancies_batch_ui_task

    if is_autorespond_cancelled_sync(chat_id, task_key):
        await callback.answer(
            i18n.get("progress-refresh-cancelled"),
            show_alert=True,
        )
        return

    full = load_hh_ui_batch_checkpoint_full_sync(chat_id, task_key)
    tail_items = load_autorespond_ui_tail_sync(chat_id, task_key) or []

    items: list[dict] = []
    resume: dict | None = None
    if full:
        items, resume = full
    if not resume:
        resume = load_hh_ui_resume_envelope_sync(chat_id, task_key)
    if not resume:
        resume = await build_hh_ui_resume_envelope_fallback_async(
            async_session_factory, chat_id, task_key
        )
    if not resume:
        await callback.answer(
            i18n.get("progress-refresh-no-resume"),
            show_alert=True,
        )
        return
    if not items:
        items = list(tail_items)
    if not items:
        await callback.answer(
            i18n.get("progress-refresh-nothing"),
            show_alert=True,
        )
        return

    active_id = get_hh_ui_batch_active_sync(chat_id, task_key)
    if active_id:
        if celery_task_id_is_active(active_id):
            await run_sync_in_thread(
                celery_app.control.revoke,
                active_id,
                terminate=True,
            )
        clear_hh_ui_batch_active_sync(chat_id, task_key)

    res = await run_celery_task(
        apply_to_vacancies_batch_ui_task,
        **{**resume, "items": items},
    )
    new_id = getattr(res, "id", None)
    if new_id:
        await svc.update_celery_task_id(task_key, str(new_id))
    await callback.answer(
        i18n.get("progress-refresh-restarted"),
        show_alert=True,
    )


@router.callback_query(
    or_f(
        F.data.startswith(PROGRESS_CANCEL_PREFIX),
        F.data.startswith(PROGRESS_CANCEL_SHORT_PREFIX),
    )
)
async def handle_progress_cancel(
    callback: CallbackQuery,
    user: User,
    i18n: I18nContext,
) -> None:
    """Revoke the Celery task and remove it from the progress bar."""
    chat_id = callback.message.chat.id if callback.message else None
    if chat_id is None or chat_id != user.telegram_id:
        await callback.answer()
        return

    redis = create_progress_redis()
    try:
        task_key = await _parse_task_key_for_progress_callback(
            redis,
            chat_id,
            callback.data or "",
            long_prefix=PROGRESS_CANCEL_PREFIX,
            short_prefix=PROGRESS_CANCEL_SHORT_PREFIX,
        )
        if not task_key:
            await callback.answer()
            return

        svc = ProgressService(
            callback.bot,
            chat_id,
            redis,
            user.language_code or "ru",
        )

        raw = await redis.get(svc._task_key(task_key))
        if not raw:
            await callback.answer(
                i18n.get("progress-task-already-finished"),
                show_alert=True,
            )
            return

        state = json.loads(raw)
        celery_task_id = normalize_celery_task_id(state.get("celery_task_id"))
        child_celery_task_id = normalize_celery_task_id(state.get("child_celery_task_id"))

        if not celery_task_id:
            if task_key.startswith("autorespond:"):
                await set_autorespond_cancelled(chat_id, task_key)
                await clear_autorespond_done_counter(chat_id, task_key)
                await clear_autorespond_failed_counter(chat_id, task_key)
                clear_hh_ui_batch_checkpoint_sync(chat_id, task_key)
                clear_hh_ui_resume_envelope_sync(chat_id, task_key)
                clear_autorespond_ui_tail_sync(chat_id, task_key)
                set_user_cancelled_sync(chat_id, task_key)
                await svc.cancel_task(task_key)
                await callback.answer(
                    i18n.get("progress-task-cancelled"),
                    show_alert=True,
                )
                return
            set_user_cancelled_sync(chat_id, task_key)
            await svc.cancel_task(task_key)
            await callback.answer(
                i18n.get("progress-task-cancelled"),
                show_alert=True,
            )
            return

        if task_key.startswith("autorespond:"):
            await set_autorespond_cancelled(chat_id, task_key)
            await clear_autorespond_done_counter(chat_id, task_key)
            clear_hh_ui_batch_checkpoint_sync(chat_id, task_key)
            clear_hh_ui_resume_envelope_sync(chat_id, task_key)
            clear_autorespond_ui_tail_sync(chat_id, task_key)

        if child_celery_task_id:
            await run_sync_in_thread(
                celery_app.control.revoke,
                child_celery_task_id,
                terminate=True,
            )
        await run_sync_in_thread(
            celery_app.control.revoke,
            celery_task_id,
            terminate=True,
        )
        set_user_cancelled_sync(chat_id, task_key)
        await svc.cancel_task(task_key)

        await callback.answer(
            i18n.get("progress-task-cancelled"),
            show_alert=True,
        )
    except Exception:
        await callback.answer()
        raise
    finally:
        await redis.aclose()
