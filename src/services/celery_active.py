"""Detect whether a Celery task id is still running on a worker."""

from __future__ import annotations

from src.core.logging import get_logger
from src.worker.app import celery_app

logger = get_logger(__name__)


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
