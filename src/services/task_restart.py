"""Re-enqueue pending and processing tasks on bot startup.

When the bot restarts (e.g. via docker compose up -d --build), Celery workers
are killed and in-flight tasks are lost. This module finds ParsingCompany
records stuck in pending/processing and re-enqueues them so they resume
from their Redis checkpoint when available.

It also resumes ``hh_ui.apply_to_vacancies_batch`` runs from Redis checkpoints
when the worker died mid-batch (resume payload + remaining items).
"""

from __future__ import annotations

from src.core.celery_async import run_celery_task
from src.core.logging import get_logger
from src.core.redis import create_sync_redis
from src.db.engine import async_session_factory
from src.infrastructure.checkpoints.redis_checkpoint_store import (
    HH_UI_APPLY_BATCH_CHECKPOINT_PREFIX,
)
from src.repositories.app_settings import AppSettingRepository
from src.repositories.parsing import ParsingCompanyRepository
from src.worker.tasks.parsing import run_parsing_company

logger = get_logger(__name__)

_HH_UI_CP_PREFIX = HH_UI_APPLY_BATCH_CHECKPOINT_PREFIX


def _parse_hh_ui_checkpoint_key(key: str) -> tuple[int, str] | None:
    p = _HH_UI_CP_PREFIX
    if not key.startswith(p):
        return None
    rest = key[len(p) :]
    first, _, task_rest = rest.partition(":")
    if not first or not task_rest:
        return None
    try:
        return int(first), task_rest
    except ValueError:
        return None


def _scan_redis_keys(pattern: str):
    r = create_sync_redis()
    try:
        cursor = 0
        while True:
            cursor, keys = r.scan(cursor, match=pattern, count=128)
            for k in keys:
                yield k
            if cursor == 0:
                break
    finally:
        r.close()


async def resume_hh_ui_batches_from_checkpoints() -> int:
    """Re-enqueue HH UI batch tasks from Redis checkpoints that have a resume envelope.

    Skips checkpoints whose ``resume`` is missing (legacy), empty, or cancelled
    when the batch is still running on a worker.
    """
    from src.db.engine import async_session_factory
    from src.services.autorespond_progress import (
        build_hh_ui_resume_envelope_fallback_async,
        clear_hh_ui_batch_active_sync,
        get_hh_ui_batch_active_sync,
        is_autorespond_cancelled_sync,
        load_hh_ui_batch_checkpoint_full_sync,
        load_hh_ui_resume_envelope_sync,
    )
    from src.services.celery_active import celery_task_id_is_active
    from src.worker.tasks.hh_ui_apply import apply_to_vacancies_batch_ui_task

    enqueued = 0
    for key in _scan_redis_keys(f"{_HH_UI_CP_PREFIX}*"):
        parsed = _parse_hh_ui_checkpoint_key(key)
        if not parsed:
            continue
        chat_id, task_key = parsed
        full = load_hh_ui_batch_checkpoint_full_sync(chat_id, task_key)
        if not full:
            continue
        items, resume = full
        if not resume:
            resume = load_hh_ui_resume_envelope_sync(chat_id, task_key)
        if not resume:
            resume = await build_hh_ui_resume_envelope_fallback_async(
                async_session_factory, chat_id, task_key
            )
        if not items or not resume:
            continue
        if is_autorespond_cancelled_sync(chat_id, task_key):
            continue
        active_id = get_hh_ui_batch_active_sync(chat_id, task_key)
        if active_id and celery_task_id_is_active(active_id):
            logger.info(
                "hh_ui_checkpoint_resume_skip_active",
                chat_id=chat_id,
                task_key=task_key,
                active_id=active_id,
            )
            continue
        if active_id:
            clear_hh_ui_batch_active_sync(chat_id, task_key)
        await run_celery_task(
            apply_to_vacancies_batch_ui_task,
            **{**resume, "items": items},
        )
        enqueued += 1
        logger.info(
            "hh_ui_checkpoint_resume_enqueued",
            chat_id=chat_id,
            task_key=task_key,
            remaining=len(items),
        )
    return enqueued


async def restart_pending_parsing_tasks() -> int:
    """Re-enqueue all ParsingCompany with status pending or processing.

    Returns the number of tasks enqueued. Skips when task_parsing_enabled
    is False. Uses run_celery_task to avoid blocking the event loop.
    """
    async with async_session_factory() as session:
        settings_repo = AppSettingRepository(session)
        enabled = await settings_repo.get_value("task_parsing_enabled", default=True)
        if not enabled:
            logger.info("Parsing task disabled, skipping restart of pending tasks")
            return 0

        company_repo = ParsingCompanyRepository(session)
        companies = await company_repo.get_pending_or_processing()

    enqueued = 0
    for company in companies:
        if not company.user:
            logger.warning(
                "Skipping parsing company with missing user",
                company_id=company.id,
                user_id=company.user_id,
            )
            continue

        await run_celery_task(
            run_parsing_company,
            company.id,
            company.user_id,
            include_blacklisted=False,
            telegram_chat_id=company.user.telegram_id,
        )
        enqueued += 1
        logger.info(
            "Re-enqueued parsing task",
            company_id=company.id,
            user_id=company.user_id,
        )

    return enqueued
