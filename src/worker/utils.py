"""Shared utilities for Celery worker tasks."""

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import settings


def _create_task_session_factory() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Create a fresh engine + session factory scoped to a single task invocation.

    Each Celery task thread gets its own event loop via asyncio.run().
    asyncpg connections are bound to the loop they were created on, so sharing
    a module-level engine across threads causes "attached to a different loop"
    errors.  A per-invocation engine avoids this entirely.
    """
    eng = create_async_engine(
        settings.database_url,
        echo=False,
        pool_size=5,
        max_overflow=10,
    )
    factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    return eng, factory


def run_async(
    task_fn: Callable[[async_sessionmaker[AsyncSession]], Coroutine[Any, Any, Any]],
) -> Any:
    """Run an async task function with an isolated DB engine.

    *task_fn* receives a session factory and returns a coroutine.
    The engine is disposed after the coroutine finishes, regardless of outcome.
    """

    async def _run() -> Any:
        engine, session_factory = _create_task_session_factory()
        try:
            return await task_fn(session_factory)
        finally:
            await engine.dispose()

    return asyncio.run(_run())
