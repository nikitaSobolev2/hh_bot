import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from src.core.logging import get_logger

logger = get_logger(__name__)

_RATE_LIMIT_SECONDS = 0.5
_CLEANUP_THRESHOLD = 5000
_STALE_SECONDS = 300.0


class ThrottleMiddleware(BaseMiddleware):
    """In-memory per-user throttle with periodic cleanup of stale entries."""

    def __init__(self, rate_limit: float = _RATE_LIMIT_SECONDS) -> None:
        self._rate_limit = rate_limit
        self._last_request: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)

        tg_user = None
        if event.message and event.message.from_user:
            tg_user = event.message.from_user
        elif event.callback_query and event.callback_query.from_user:
            tg_user = event.callback_query.from_user

        if tg_user is None:
            return await handler(event, data)

        now = time.monotonic()
        last = self._last_request.get(tg_user.id, 0.0)
        if now - last < self._rate_limit:
            logger.debug("Throttled user", telegram_id=tg_user.id)
            return None

        self._last_request[tg_user.id] = now

        if len(self._last_request) > _CLEANUP_THRESHOLD:
            self._last_request = {
                uid: ts
                for uid, ts in self._last_request.items()
                if now - ts < _STALE_SECONDS
            }

        return await handler(event, data)
