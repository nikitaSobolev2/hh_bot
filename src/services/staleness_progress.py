"""Redis-backed progress timestamp for staleness detection in long-running tasks.

Used by the parsing task to detect when no progress (vacancy processed, page scraped)
has occurred within a configurable window. If stale, the task is terminated instead
of retrying from scratch.

Redis key: progress:stale:{task_key} = Unix timestamp (float) as string
TTL: 4 hours
"""

from __future__ import annotations

import time

_TTL = 4 * 3600
_KEY_PREFIX = "progress:stale:"


def _redis_key(task_key: str) -> str:
    return f"{_KEY_PREFIX}{task_key}"


async def record_progress(redis, task_key: str) -> None:
    """Record that progress occurred for the given task."""
    await redis.set(_redis_key(task_key), str(time.time()), ex=_TTL)


async def get_last_progress(redis, task_key: str) -> float | None:
    """Return the last progress timestamp, or None if absent."""
    raw = await redis.get(_redis_key(task_key))
    if not raw:
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


async def is_stale(redis, task_key: str, window_seconds: float) -> bool:
    """Return True if no progress has occurred within window_seconds."""
    last = await get_last_progress(redis, task_key)
    if last is None:
        return False
    return (time.time() - last) > window_seconds


def create_staleness_redis():
    """Create an async Redis client for staleness progress."""
    from src.core.redis import create_async_redis

    return create_async_redis()
