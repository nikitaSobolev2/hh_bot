"""Redis-backed sliding-window rate limiter for external API calls.

Prevents HH.ru scraping and OpenAI API calls from exceeding rate limits.

Usage
-----
    from src.worker.throttle import RateLimiter
    from src.core.redis import create_async_redis

    redis = create_async_redis()
    limiter = RateLimiter(redis, namespace="hh", max_requests=5, window_seconds=1)

    await limiter.acquire()  # blocks until a token is available
    response = await http_client.get(url)

The limiter uses a sliding-window counter implemented with INCR + EXPIRE.
This is not strictly atomic but is acceptable for rate limiting — occasional
bursts of N+1 requests are benign compared to the alternative of a Lua-script
overhead on every call.
"""

from __future__ import annotations

import asyncio
import time

from src.core.logging import get_logger

logger = get_logger(__name__)

_POLL_INTERVAL = 0.1  # seconds between retry checks


class RateLimiter:
    """Sliding-window rate limiter backed by Redis.

    Allows at most ``max_requests`` per ``window_seconds``.
    ``acquire()`` blocks (with async sleep) until a slot is available.
    """

    def __init__(
        self,
        redis,
        *,
        namespace: str,
        max_requests: int,
        window_seconds: int = 1,
    ) -> None:
        self._redis = redis
        self._namespace = namespace
        self._max_requests = max_requests
        self._window_seconds = window_seconds

    async def acquire(self) -> None:
        """Block until a request slot is available within the rate window."""
        while True:
            allowed = await self._try_acquire()
            if allowed:
                return
            logger.debug(
                "Rate limit reached, waiting",
                namespace=self._namespace,
                max=self._max_requests,
                window=self._window_seconds,
            )
            await asyncio.sleep(_POLL_INTERVAL)

    async def _try_acquire(self) -> bool:
        """Attempt to claim one request slot. Returns True on success."""
        window_key = self._window_key()
        count = await self._redis.incr(window_key)
        if count == 1:
            await self._redis.expire(window_key, self._window_seconds)
        if count <= self._max_requests:
            return True
        await self._redis.decr(window_key)
        return False

    def _window_key(self) -> str:
        """Key scoped to the current time window bucket."""
        bucket = int(time.time()) // self._window_seconds
        return f"throttle:{self._namespace}:w{bucket}"
