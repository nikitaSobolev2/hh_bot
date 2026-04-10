"""Detect whether a Celery task id is still running on a worker."""

from __future__ import annotations

from src.core.logging import get_logger
from src.worker.app import celery_app

logger = get_logger(__name__)


def celery_task_id_known_to_workers(task_id: str) -> bool | None:
    """Whether ``task_id`` appears in any worker's active or reserved task lists.

    Returns:
        ``True`` if the id is listed (task may still be running).
        ``False`` if inspect succeeded and at least one list response was obtained
        but the id was not found (safe to treat Redis lease as stale after crash).
        ``None`` if workers could not be inspected (do **not** override locks).
    """
    if not task_id:
        return False
    try:
        insp = celery_app.control.inspect(timeout=1.0)
        if insp is None:
            return None
        any_response = False
        for name in ("active", "reserved"):
            fn = getattr(insp, name, None)
            if not callable(fn):
                continue
            data = fn()
            if data is not None:
                any_response = True
            if not data:
                continue
            for tasks in data.values():
                for t in tasks or []:
                    if isinstance(t, dict) and t.get("id") == task_id:
                        return True
        if not any_response:
            return None
        return False
    except Exception as exc:
        logger.warning("celery_inspect_known_workers_failed", error=str(exc)[:200])
        return None


def celery_task_id_is_active(task_id: str) -> bool:
    """Return True if ``task_id`` appears in any worker's ``inspect().active()`` list."""
    if not task_id:
        return False
    try:
        insp = celery_app.control.inspect(timeout=1.0)
        if insp is None:
            return False
        active = insp.active()
        if not active:
            return False
        for tasks in active.values():
            for t in tasks or []:
                if isinstance(t, dict) and t.get("id") == task_id:
                    return True
        return False
    except Exception as exc:
        logger.warning("celery_inspect_active_failed", error=str(exc)[:200])
        return False
