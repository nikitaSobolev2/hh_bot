"""Shared utilities for Celery worker tasks."""

import asyncio
from collections.abc import Coroutine
from typing import Any


async def _run_and_dispose(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run the coroutine and dispose the DB engine pool before the loop closes.

    asyncio.run() destroys the event loop on exit, which invalidates any
    asyncpg connections still sitting in the pool. Disposing the engine
    while the loop is alive prevents the next task from grabbing a stale
    connection whose transport already lost its proactor.
    """
    try:
        return await coro
    finally:
        from src.db.engine import engine

        await engine.dispose()


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run an async coroutine from a synchronous Celery task context."""
    return asyncio.run(_run_and_dispose(coro))
