"""Per-user daily limit for HH login assist (Redis, sync for Celery)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import redis as sync_redis

from src.config import settings


def _key(user_id: int) -> str:
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    return f"hh_login_assist:{user_id}:{day}"


def _seconds_until_utc_midnight() -> int:
    now = datetime.now(UTC)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((tomorrow - now).total_seconds()))


def try_acquire_login_assist_slot_sync(user_id: int) -> bool:
    """Return True if under daily limit (increments counter)."""
    limit = int(settings.hh_login_assist_max_per_day)
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
