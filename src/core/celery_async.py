"""Run Celery tasks and control commands from async code without blocking the event loop.

Celery's task.delay() and app.control.revoke() use synchronous Redis/AMQP calls
that block the asyncio event loop. This module provides async wrappers that run
them in a thread pool.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any


def normalize_celery_task_id(task_id: object | None) -> str | None:
    """Return a string id safe for ``app.control.revoke``.

    Celery joins revoked ids with `', '.join(task_ids)` and requires ``str``.
    Values from JSON, Redis, or ORM may be ``int`` or ``bytes``.
    """
    if task_id is None:
        return None
    if isinstance(task_id, bytes):
        s = task_id.decode("utf-8", errors="replace").strip()
        return s if s else None
    s = str(task_id).strip()
    return s if s else None


async def run_celery_task(
    task: Any,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Run task.delay(*args, **kwargs) in a thread so it does not block the event loop."""
    return await asyncio.to_thread(
        lambda: task.delay(*args, **kwargs),
    )


async def run_sync_in_thread[**P, T](fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    """Run any sync callable in a thread pool."""
    return await asyncio.to_thread(fn, *args, **kwargs)
