"""Handlers for progress bar actions (e.g. cancel task)."""

from aiogram import F, Router
from aiogram.types import CallbackQuery

from src.core.celery_async import run_sync_in_thread
from src.core.i18n import I18nContext
from src.models.user import User
from src.services.autorespond_progress import (
    clear_autorespond_done_counter,
    set_autorespond_cancelled,
)
from src.services.progress_service import ProgressService, create_progress_redis
from src.worker.app import celery_app

router = Router(name="progress")

_PROGRESS_CANCEL_PREFIX = "prog:cancel:"


def _parse_task_key_from_callback(data: str) -> str | None:
    """Extract task_key from callback_data. Format: prog:cancel:{encoded_key}."""
    if not data or not data.startswith(_PROGRESS_CANCEL_PREFIX):
        return None
    encoded = data[len(_PROGRESS_CANCEL_PREFIX) :]
    return encoded.replace("_", ":") if encoded else None


@router.callback_query(F.data.startswith(_PROGRESS_CANCEL_PREFIX))
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

    task_key = _parse_task_key_from_callback(callback.data or "")
    if not task_key:
        await callback.answer()
        return

    redis = create_progress_redis()
    try:
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

        import json

        state = json.loads(raw)
        celery_task_id = state.get("celery_task_id")
        if not celery_task_id:
            await callback.answer(
                i18n.get("progress-task-already-finished"),
                show_alert=True,
            )
            return

        # Stop chained autorespond work (cover_letter / hh_ui tasks) — parent may already be done.
        await set_autorespond_cancelled(chat_id, task_key)
        await clear_autorespond_done_counter(chat_id, task_key)

        await run_sync_in_thread(
            celery_app.control.revoke,
            celery_task_id,
            terminate=True,
        )
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
