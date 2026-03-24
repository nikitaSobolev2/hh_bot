"""Per-user daily rate limit for HH UI apply (Redis)."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import redis as sync_redis

from src.config import settings
from src.core.constants import AppSettingKey
from src.core.redis import create_async_redis

_LIMIT_CACHE_TTL_SEC = 5.0
_limit_cache_monotonic: float | None = None
_limit_cache_value: int | None = None


def _coerce_hh_ui_apply_max_per_day(value: object, fallback: int) -> int:
    """Normalize DB JSON to int (same rules as ``sync_setting_to_runtime`` for ints)."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return int(value)
    if isinstance(value, str) and value.strip() != "":
        try:
            return int(value.strip())
        except ValueError:
            return fallback
    return fallback


def _fetch_hh_ui_apply_max_per_day_from_db() -> int | None:
    """Read current cap from ``app_settings``; ``None`` if missing or on error."""
    try:
        import psycopg
    except ImportError:
        return None
    try:
        with psycopg.connect(
            settings.database_url_sync,
            connect_timeout=5,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT value FROM app_settings WHERE key = %s",
                    (AppSettingKey.HH_UI_APPLY_MAX_PER_DAY,),
                )
                row = cur.fetchone()
    except Exception:
        return None
    if row is None or row[0] is None:
        return None
    return _coerce_hh_ui_apply_max_per_day(row[0], int(settings.hh_ui_apply_max_per_day))


def get_hh_ui_apply_max_per_day_effective() -> int:
    """Daily cap from DB (admin), cached briefly.

    Celery workers only load ``settings`` at process start; this reads the live DB value
    so admin changes apply without restarting workers. ``0`` means unlimited.
    """
    global _limit_cache_monotonic, _limit_cache_value
    now = time.monotonic()
    if (
        _limit_cache_value is not None
        and _limit_cache_monotonic is not None
        and now - _limit_cache_monotonic < _LIMIT_CACHE_TTL_SEC
    ):
        return _limit_cache_value
    db_val = _fetch_hh_ui_apply_max_per_day_from_db()
    resolved = int(db_val if db_val is not None else settings.hh_ui_apply_max_per_day)
    _limit_cache_value = resolved
    _limit_cache_monotonic = now
    return resolved


def _get_limit() -> int:
    return get_hh_ui_apply_max_per_day_effective()


def _key(user_id: int) -> str:
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    return f"hh_ui_apply:{user_id}:{day}"


def _seconds_until_utc_midnight() -> int:
    now = datetime.now(UTC)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((tomorrow - now).total_seconds()))


async def try_acquire_ui_apply_slot_async(user_id: int) -> bool:
    """Return True if the user is under the daily limit (increments counter)."""
    limit = _get_limit()
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
    limit = _get_limit()
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
    limit = _get_limit()
    if limit <= 0:
        return None
    return max(0, limit - current_ui_apply_count_sync(user_id))
