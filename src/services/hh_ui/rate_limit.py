"""Per-user daily rate limit for HH UI apply (Redis)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import redis as sync_redis

from src.config import settings
from src.core.redis import create_async_redis


def _key(user_id: int) -> str:
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    return f"hh_ui_apply:{user_id}:{day}"


def _seconds_until_utc_midnight() -> int:
    now = datetime.now(UTC)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((tomorrow - now).total_seconds()))


async def try_acquire_ui_apply_slot_async(user_id: int) -> bool:
    """Return True if the user is under the daily limit (increments counter)."""
    limit = int(settings.hh_ui_apply_max_per_day)
    if limit <= 0:
        return True
    r = create_async_redis()
    try:
        key = _key(user_id)
        n = int(await r.incr(key))
        ttl = await r.ttl(key)
        if ttl == -1:
            await r.expire(key, _seconds_until_utc_midnight())
        if n > limit:
            await r.decr(key)
            return False
        return True
    finally:
        await r.aclose()


def try_acquire_ui_apply_slot_sync(user_id: int) -> bool:
    """Sync variant for Celery / threaded code."""
    limit = int(settings.hh_ui_apply_max_per_day)
    if limit <= 0:
        return True
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        key = _key(user_id)
        n = int(r.incr(key))
        ttl = r.ttl(key)
        if ttl == -1:
            r.expire(key, _seconds_until_utc_midnight())
        if n > limit:
            r.decr(key)
            return False
        return True
    finally:
        r.close()


def current_ui_apply_count_sync(user_id: int) -> int:
    """How many UI apply slots were consumed today (Redis counter), without incrementing."""
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        raw = r.get(_key(user_id))
        return int(raw) if raw is not None else 0
    finally:
        r.close()


def remaining_ui_apply_slots_sync(user_id: int) -> int | None:
    """Slots left for today under ``hh_ui_apply_max_per_day``; ``None`` if unlimited (limit <= 0)."""
    limit = int(settings.hh_ui_apply_max_per_day)
    if limit <= 0:
        return None
    return max(0, limit - current_ui_apply_count_sync(user_id))
