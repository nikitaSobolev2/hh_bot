"""Autorespond + UI apply: shared progress bar until each Playwright/API step completes."""

from __future__ import annotations

from typing import Any

import redis as sync_redis

from src.config import settings
from src.core.logging import get_logger
from src.services.progress_service import ProgressService, create_progress_redis

logger = get_logger(__name__)

_DONE_TTL_S = 4 * 3600


def autorespond_done_redis_key(chat_id: int, task_key: str) -> str:
    return f"progress:autorespond_done:{chat_id}:{task_key}"


def autorespond_cancel_redis_key(chat_id: int, task_key: str) -> str:
    return f"progress:autorespond_cancel:{chat_id}:{task_key}"


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
    try:
        await svc.update_bar(task_key, 0, display_done, total)
        if footer_failed_line:
            await svc.update_footer(task_key, [footer_failed_line])
    except Exception as exc:
        # Telegram / aiohttp timeouts or SSL stalls must not abort autorespond (SoftTimeLimitExceeded).
        logger.warning(
            "autorespond_progress_bar_update_failed",
            error=str(exc)[:400],
            chat_id=chat_id,
            task_key=task_key,
        )

    if done >= total:
        try:
            await svc.finish_task(task_key)
        except Exception as exc:
            logger.warning(
                "autorespond_progress_finish_failed",
                error=str(exc)[:400],
                chat_id=chat_id,
                task_key=task_key,
            )
        await redis.delete(key)
        return True
    return False
