"""Autorespond + UI apply: shared progress bar until each Playwright/API step completes."""

from __future__ import annotations

from typing import Any

from src.services.progress_service import ProgressService, create_progress_redis

_DONE_TTL_S = 4 * 3600


def autorespond_done_redis_key(chat_id: int, task_key: str) -> str:
    return f"progress:autorespond_done:{chat_id}:{task_key}"


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
    await svc.update_bar(task_key, 0, display_done, total)
    if footer_failed_line:
        await svc.update_footer(task_key, [footer_failed_line])

    if done >= total:
        await svc.finish_task(task_key)
        await redis.delete(key)
        return True
    return False
