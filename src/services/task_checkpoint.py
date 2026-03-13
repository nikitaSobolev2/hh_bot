"""Redis-backed checkpoint for resumable Celery tasks.

Stores ``{task_id, analyzed, total}`` under a namespaced key so that a
re-delivered task can restore its progress bar position and skip already-
committed work.

Usage
-----
    redis = create_progress_redis()
    cp = TaskCheckpointService(redis)

    # Save after each unit of work:
    await cp.save("autoparse:42", task_id="abc-123", analyzed=33, total=86)

    # Restore on restart (returns None when no matching checkpoint exists):
    result = await cp.load("autoparse:42", task_id="abc-123")
    if result:
        analyzed_offset, original_total = result

    # Clear on successful completion:
    await cp.clear("autoparse:42")
"""

from __future__ import annotations

import json

_TTL = 4 * 3600
_KEY_PREFIX = "checkpoint:"


def create_checkpoint_redis():
    """Create an async Redis client for TaskCheckpointService."""
    from src.core.redis import create_async_redis

    return create_async_redis()


class TaskCheckpointService:
    """Persist and restore per-task progress counters in Redis.

    The ``task_id`` guard ensures a checkpoint written by one Celery task
    execution is never mistakenly applied to a different execution of the same
    logical task (e.g. a manual re-trigger while an older checkpoint exists).
    """

    def __init__(self, redis) -> None:
        self._redis = redis

    async def save(self, key: str, task_id: str, *, analyzed: int, total: int) -> None:
        """Persist progress counters for ``key``, tagged with ``task_id``."""
        payload = json.dumps({"task_id": task_id, "analyzed": analyzed, "total": total})
        await self._redis.set(self._redis_key(key), payload, ex=_TTL)

    async def load(self, key: str, task_id: str) -> tuple[int, int] | None:
        """Return ``(analyzed, total)`` if a matching checkpoint exists.

        Returns ``None`` when the key is absent or belongs to a different task.
        """
        raw = await self._redis.get(self._redis_key(key))
        if not raw:
            return None
        data = json.loads(raw)
        if data.get("task_id") != task_id:
            return None
        return data["analyzed"], data["total"]

    async def clear(self, key: str) -> None:
        """Remove the checkpoint entry after successful task completion."""
        await self._redis.delete(self._redis_key(key))

    def _redis_key(self, key: str) -> str:
        return f"{_KEY_PREFIX}{key}"
