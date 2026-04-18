"""Shared Redis client factories.

All services that need a Redis connection should use helpers from this module.
This keeps URL/pool settings consistent and lets Celery tasks record Redis
usage metrics without changing command behavior.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import time
import weakref
from typing import Any

import redis
import redis.asyncio as aioredis

from src.config import settings
from src.worker.task_metrics import record_redis_client, record_redis_command

_SYNC_POOL: redis.ConnectionPool | None = None
_SYNC_POOL_PID: int | None = None
# Async Redis connections are bound to the event loop they were created on.
# Celery tasks use ``asyncio.run()`` per invocation, so a process-wide pool
# (or PID-scoped pool) leaves connections attached to a closed loop and causes
# "Future attached to a different loop" / "Event loop is closed" on the next task.
_AsyncPoolByLoop = weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, aioredis.ConnectionPool]
_ASYNC_POOL_BY_LOOP: _AsyncPoolByLoop = weakref.WeakKeyDictionary()


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
        if entered is not self._client:
            return _InstrumentedRedisProxy(entered, kind=self._kind)
        return self

    def __exit__(self, exc_type, exc, tb) -> Any:
        return self._client.__exit__(exc_type, exc, tb)

    async def __aenter__(self) -> Any:
        entered = await self._client.__aenter__()
        if entered is not self._client:
            return _InstrumentedRedisProxy(entered, kind=self._kind)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> Any:
        return await self._client.__aexit__(exc_type, exc, tb)


def _get_sync_pool() -> redis.ConnectionPool:
    global _SYNC_POOL, _SYNC_POOL_PID
    pid = os.getpid()
    if _SYNC_POOL is None or pid != _SYNC_POOL_PID:
        _SYNC_POOL = redis.ConnectionPool.from_url(settings.redis_url, decode_responses=True)
        _SYNC_POOL_PID = pid
    return _SYNC_POOL


def _async_pool_for_running_loop() -> aioredis.ConnectionPool:
    loop = asyncio.get_running_loop()
    pool = _ASYNC_POOL_BY_LOOP.get(loop)
    if pool is None:
        pool = aioredis.ConnectionPool.from_url(settings.redis_url, decode_responses=True)
        _ASYNC_POOL_BY_LOOP[loop] = pool
    return pool


def create_sync_redis():
    """Create a sync Redis client backed by a per-process shared pool."""
    client = redis.Redis(connection_pool=_get_sync_pool())
    return _InstrumentedRedisProxy(client, kind="sync")


def create_async_redis():
    """Create an async Redis client from application settings.

    Returns a ``redis.asyncio.Redis`` instance with:
    - ``decode_responses=True`` — all keys and values are native Python strings
    - URL from ``settings.redis_url``

    When created inside a running event loop, clients share a **loop-local**
    connection pool so Celery's repeated ``asyncio.run()`` usage stays safe.

    With no running loop, the client owns a dedicated pool (first use binds to
    whatever loop later runs the coroutine).

    Callers are responsible for closing the connection when done.
    """
    try:
        pool = _async_pool_for_running_loop()
    except RuntimeError:
        # No loop yet: let the client own its pool so ``aclose()`` can dispose it.
        client = aioredis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
    else:
        # Explicit shared pool: redis-py 5 does not auto-close it on ``aclose()``.
        client = aioredis.Redis(connection_pool=pool)
    return _InstrumentedRedisProxy(client, kind="async")
