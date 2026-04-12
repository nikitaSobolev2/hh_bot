"""Shared Redis client factories.

All services that need a Redis connection should use helpers from this module.
This keeps URL/pool settings consistent and lets Celery tasks record Redis
usage metrics without changing command behavior.
"""

from __future__ import annotations

import inspect
import os
import time
from typing import Any

import redis
import redis.asyncio as aioredis

from src.config import settings
from src.worker.task_metrics import record_redis_client, record_redis_command


_SYNC_POOL: redis.ConnectionPool | None = None
_SYNC_POOL_PID: int | None = None
_ASYNC_POOL: aioredis.ConnectionPool | None = None
_ASYNC_POOL_PID: int | None = None


class _InstrumentedRedisProxy:
    def __init__(self, client: Any, *, kind: str) -> None:
        self._client = client
        self._kind = kind
        record_redis_client(kind)

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._client, name)
        if not callable(attr):
            return attr

        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            started_at = time.perf_counter()
            try:
                result = attr(*args, **kwargs)
            except Exception:
                record_redis_command(
                    self._kind,
                    command=name,
                    elapsed_ms=(time.perf_counter() - started_at) * 1000,
                )
                raise

            if inspect.isawaitable(result):

                async def _await_result() -> Any:
                    try:
                        awaited = await result
                    finally:
                        record_redis_command(
                            self._kind,
                            command=name,
                            elapsed_ms=(time.perf_counter() - started_at) * 1000,
                        )
                    if awaited is self._client:
                        return self
                    if name == "pipeline":
                        return _InstrumentedRedisProxy(awaited, kind=self._kind)
                    return awaited

                return _await_result()

            record_redis_command(
                self._kind,
                command=name,
                elapsed_ms=(time.perf_counter() - started_at) * 1000,
            )
            if result is self._client:
                return self
            if name == "pipeline":
                return _InstrumentedRedisProxy(result, kind=self._kind)
            return result

        return _wrapped

    def __enter__(self) -> Any:
        entered = self._client.__enter__()
        return _InstrumentedRedisProxy(entered, kind=self._kind) if entered is not self._client else self

    def __exit__(self, exc_type, exc, tb) -> Any:
        return self._client.__exit__(exc_type, exc, tb)

    async def __aenter__(self) -> Any:
        entered = await self._client.__aenter__()
        return _InstrumentedRedisProxy(entered, kind=self._kind) if entered is not self._client else self

    async def __aexit__(self, exc_type, exc, tb) -> Any:
        return await self._client.__aexit__(exc_type, exc, tb)


def _get_sync_pool() -> redis.ConnectionPool:
    global _SYNC_POOL, _SYNC_POOL_PID
    pid = os.getpid()
    if _SYNC_POOL is None or _SYNC_POOL_PID != pid:
        _SYNC_POOL = redis.ConnectionPool.from_url(settings.redis_url, decode_responses=True)
        _SYNC_POOL_PID = pid
    return _SYNC_POOL


def _get_async_pool() -> aioredis.ConnectionPool:
    global _ASYNC_POOL, _ASYNC_POOL_PID
    pid = os.getpid()
    if _ASYNC_POOL is None or _ASYNC_POOL_PID != pid:
        _ASYNC_POOL = aioredis.ConnectionPool.from_url(settings.redis_url, decode_responses=True)
        _ASYNC_POOL_PID = pid
    return _ASYNC_POOL


def create_sync_redis():
    """Create a sync Redis client backed by a per-process shared pool."""
    client = redis.Redis(connection_pool=_get_sync_pool())
    return _InstrumentedRedisProxy(client, kind="sync")


def create_async_redis():
    """Create an async Redis client from application settings.

    Returns a ``redis.asyncio.Redis`` instance with:
    - ``decode_responses=True`` — all keys and values are native Python strings
    - URL from ``settings.redis_url``

    Callers are responsible for closing the connection when done.
    """
    client = aioredis.Redis(connection_pool=_get_async_pool())
    return _InstrumentedRedisProxy(client, kind="async")
