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

from typing import Any

from src.application.ports.checkpoints import CheckpointStore
from src.infrastructure.checkpoints.redis_checkpoint_store import (
    RedisCheckpointStore,
    task_checkpoint_key,
    task_group_checkpoint_key,
)


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

    def __init__(self, redis, store: CheckpointStore | None = None) -> None:
        self._redis = redis
        self._store = store or RedisCheckpointStore(redis)

    async def save(self, key: str, task_id: str, *, analyzed: int, total: int) -> None:
        """Persist progress counters for ``key``, tagged with ``task_id``."""
        await self._store.save_json(
            task_checkpoint_key(key),
            {"task_id": task_id, "analyzed": analyzed, "total": total},
        )

    async def load(self, key: str, task_id: str) -> tuple[int, int] | None:
        """Return ``(analyzed, total)`` if a matching checkpoint exists.

        Returns ``None`` when the key is absent or belongs to a different task.
        """
        data = await self._store.load_json(task_checkpoint_key(key))
        if not data:
            return None
        if data.get("task_id") != task_id:
            return None
        return data["analyzed"], data["total"]

    async def load_for_resume(self, key: str) -> tuple[int, int] | None:
        """Return ``(analyzed, total)`` when any checkpoint exists, ignoring task id."""
        data = await self._store.load_json(task_checkpoint_key(key))
        if not data:
            return None
        return int(data.get("analyzed") or 0), int(data.get("total") or 0)

    async def save_parsing(
        self,
        key: str,
        task_id: str,
        *,
        processed: int,
        total: int,
        urls: list[dict],
    ) -> None:
        """Persist parsing checkpoint with vacancy URL list for resume."""
        await self._store.save_json(
            task_checkpoint_key(key),
            {"task_id": task_id, "processed": processed, "total": total, "urls": urls},
        )

    async def load_parsing(self, key: str, task_id: str) -> tuple[int, int, list[dict]] | None:
        """Return ``(processed, total, urls)`` if a matching parsing checkpoint exists.

        Returns ``None`` when the key is absent or belongs to a different task.
        """
        data = await self._store.load_json(task_checkpoint_key(key))
        if not data:
            return None
        if data.get("task_id") != task_id:
            return None
        urls = data.get("urls", [])
        if not urls:
            return None
        return data["processed"], data["total"], urls

    async def load_parsing_for_resume(self, key: str) -> tuple[int, int, list[dict]] | None:
        """Return ``(processed, total, urls)`` if a parsing checkpoint exists, ignoring task_id.

        For resume-after-restart only: when the previous task was killed, its checkpoint
        is orphaned but valid. Caller must ensure no concurrent execution for this key.
        Returns ``None`` when the key is absent or urls are empty.
        """
        data = await self._store.load_json(task_checkpoint_key(key))
        if not data:
            return None
        urls = data.get("urls", [])
        if not urls:
            return None
        return data["processed"], data["total"], urls

    async def clear(self, key: str) -> None:
        """Remove the checkpoint entry after successful task completion."""
        await self._store.delete(task_checkpoint_key(key))

    async def save_task_group_state(
        self,
        chat_id: int,
        task_key: str,
        *,
        user_id: int,
        telegram_id: int,
        steps: list[dict[str, Any]],
        resume_from_index: int,
        results: list[dict[str, Any]] | None = None,
    ) -> None:
        """Persist task-group resume metadata for the refresh button."""
        await self._store.save_json(
            task_group_checkpoint_key(chat_id, task_key),
            {
                "user_id": user_id,
                "telegram_id": telegram_id,
                "steps": steps,
                "resume_from_index": resume_from_index,
                "results": results or [],
            },
        )

    async def load_task_group_state(self, chat_id: int, task_key: str) -> dict[str, Any] | None:
        """Load task-group resume metadata for the refresh button."""
        data = await self._store.load_json(task_group_checkpoint_key(chat_id, task_key))
        if not data:
            return None
        steps = data.get("steps")
        if not isinstance(steps, list):
            return None
        results = data.get("results")
        if not isinstance(results, list):
            results = []
        return {
            "user_id": int(data.get("user_id") or 0),
            "telegram_id": int(data.get("telegram_id") or 0),
            "steps": steps,
            "resume_from_index": int(data.get("resume_from_index") or 0),
            "results": results,
        }

    async def clear_task_group_state(self, chat_id: int, task_key: str) -> None:
        """Remove task-group resume metadata."""
        await self._store.delete(task_group_checkpoint_key(chat_id, task_key))
