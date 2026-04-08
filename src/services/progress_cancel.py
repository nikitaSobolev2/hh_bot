"""Cooperative cancellation flags for pinned progress tasks (beyond Celery revoke)."""

from __future__ import annotations

import redis as sync_redis

from src.config import settings

_CANCEL_TTL_S = 4 * 3600


def user_cancel_redis_key(chat_id: int, task_key: str) -> str:
    return f"progress:user_cancel:{chat_id}:{task_key}"


def set_user_cancelled_sync(chat_id: int, task_key: str) -> None:
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        r.set(user_cancel_redis_key(chat_id, task_key), "1", ex=_CANCEL_TTL_S)
    finally:
        r.close()


def is_user_cancelled_sync(chat_id: int, task_key: str) -> bool:
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        return bool(r.get(user_cancel_redis_key(chat_id, task_key)))
    finally:
        r.close()


def clear_user_cancelled_sync(chat_id: int, task_key: str) -> None:
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        r.delete(user_cancel_redis_key(chat_id, task_key))
    finally:
        r.close()
