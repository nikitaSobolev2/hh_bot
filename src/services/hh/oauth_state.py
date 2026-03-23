"""Redis-backed OAuth `state` for HH authorization (binds callback to Telegram user)."""

from __future__ import annotations

import secrets

from src.core.redis import create_async_redis

_STATE_PREFIX = "hh_oauth:state:"
_TTL_SEC = 900


def generate_state() -> str:
    return secrets.token_urlsafe(32)


async def store_state(state: str, telegram_user_id: int) -> None:
    r = create_async_redis()
    await r.setex(f"{_STATE_PREFIX}{state}", _TTL_SEC, str(telegram_user_id))


async def pop_telegram_user_id(state: str) -> int | None:
    if not state:
        return None
    r = create_async_redis()
    key = f"{_STATE_PREFIX}{state}"
    raw = await r.get(key)
    if raw is None:
        return None
    await r.delete(key)
    return int(raw)
