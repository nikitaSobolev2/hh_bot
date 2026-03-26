"""Autorespond + UI apply: shared progress bar until each Playwright/API step completes."""

from __future__ import annotations

from typing import Any

import redis as sync_redis

from src.config import settings
from src.core.i18n import get_text
from src.core.logging import get_logger
from src.services.progress_service import ProgressService, create_progress_redis

logger = get_logger(__name__)

_DONE_TTL_S = 4 * 3600


def autorespond_done_redis_key(chat_id: int, task_key: str) -> str:
    return f"progress:autorespond_done:{chat_id}:{task_key}"


def autorespond_cancel_redis_key(chat_id: int, task_key: str) -> str:
    return f"progress:autorespond_cancel:{chat_id}:{task_key}"


def autorespond_failed_redis_key(chat_id: int, task_key: str) -> str:
    """UI apply outcomes that are not success / already / preflight-unavailable (see hh_ui_apply)."""
    return f"progress:autorespond_failed:{chat_id}:{task_key}"


def increment_autorespond_failed_sync(chat_id: int, task_key: str, n: int = 1) -> int:
    """Increment failed counter (sync Redis; safe from Celery before async tick)."""
    if n <= 0:
        return 0
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    key = autorespond_failed_redis_key(chat_id, task_key)
    try:
        v = int(r.incrby(key, n))
        r.expire(key, _DONE_TTL_S)
        return v
    finally:
        r.close()


def is_autorespond_cancelled_sync(chat_id: int, task_key: str) -> bool:
    """Set by the progress Cancel button; checked by Celery child tasks (sync Redis)."""
    key = autorespond_cancel_redis_key(chat_id, task_key)
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        return bool(r.get(key))
    finally:
        r.close()


async def set_autorespond_cancelled(chat_id: int, task_key: str) -> None:
    """Mark autorespond run as cancelled (child tasks exit without applying)."""
    redis = create_progress_redis()
    try:
        await redis.set(autorespond_cancel_redis_key(chat_id, task_key), "1", ex=_DONE_TTL_S)
    finally:
        await redis.aclose()


async def clear_autorespond_done_counter(chat_id: int, task_key: str) -> None:
    redis = create_progress_redis()
    await redis.delete(autorespond_done_redis_key(chat_id, task_key))


async def clear_autorespond_failed_counter(chat_id: int, task_key: str) -> None:
    redis = create_progress_redis()
    await redis.delete(autorespond_failed_redis_key(chat_id, task_key))


async def tick_autorespond_bar(
    *,
    bot: Any,
    chat_id: int,
    task_key: str,
    total: int,
    locale: str,
    footer_failed_line: str | None = None,
) -> bool:
    """Increment done counter, refresh bar, finish pinned progress when done >= total.

    Returns True if the autorespond progress task was finished (all steps accounted for).
    """
    if total <= 0:
        return False

    redis = create_progress_redis()
    key = autorespond_done_redis_key(chat_id, task_key)
    done = int(await redis.incr(key))
    await redis.expire(key, _DONE_TTL_S)

    display_done = min(done, total)
    svc = ProgressService(bot, chat_id, redis, locale)

    if footer_failed_line is not None:
        footer_lines = [footer_failed_line]
    else:
        failed_n = int(
            await redis.get(autorespond_failed_redis_key(chat_id, task_key)) or 0
        )
        footer_lines = [get_text("autorespond-progress-failed", locale, count=failed_n)]
    try:
        await svc.update_bar(task_key, 0, display_done, total)
        await svc.update_footer(task_key, footer_lines)
    except Exception as exc:
        # Telegram / aiohttp timeouts or SSL stalls must not abort autorespond (SoftTimeLimitExceeded).
        logger.warning(
            "autorespond_progress_bar_update_failed",
            error=str(exc)[:400],
            chat_id=chat_id,
            task_key=task_key,
        )

    if done >= total:
        failed_n = int(await redis.get(autorespond_failed_redis_key(chat_id, task_key)) or 0)
        logger.info(
            "autorespond_progress_finish_task",
            chat_id=chat_id,
            task_key=task_key,
            done=done,
            total=total,
            failed_ui=failed_n,
        )
        finish_note = None
        if failed_n > 0:
            finish_note = get_text(
                "autorespond-progress-completed-with-failures",
                locale,
                count=failed_n,
            )
        try:
            await svc.finish_task(task_key, shortage_note=finish_note)
        except Exception as exc:
            logger.warning(
                "autorespond_progress_finish_failed",
                error=str(exc)[:400],
                chat_id=chat_id,
                task_key=task_key,
            )
        await redis.delete(key)
        await redis.delete(autorespond_failed_redis_key(chat_id, task_key))
        return True
    return False
