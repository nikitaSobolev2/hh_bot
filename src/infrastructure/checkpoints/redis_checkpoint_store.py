"""Redis-backed checkpoint store and shared key helpers."""

from __future__ import annotations

import json
from typing import Any

from src.application.ports.checkpoints import CheckpointStore

CHECKPOINT_TTL_SECONDS = 4 * 3600
_CHECKPOINT_PREFIX = "checkpoint:"
_HH_UI_APPLY_BATCH_PREFIX = "checkpoint:hh_ui_apply_batch:"
_TASKGROUP_PREFIX = "checkpoint:taskgroup:"
HH_UI_APPLY_BATCH_CHECKPOINT_PREFIX = _HH_UI_APPLY_BATCH_PREFIX


def task_checkpoint_key(key: str) -> str:
    """Redis key for generic task checkpoints."""
    return f"{_CHECKPOINT_PREFIX}{key}"


def hh_ui_apply_batch_checkpoint_key(chat_id: int, task_key: str) -> str:
    """Redis key for autorespond UI batch resume payloads."""
    return f"{_HH_UI_APPLY_BATCH_PREFIX}{chat_id}:{task_key}"


def task_group_checkpoint_key(chat_id: int, task_key: str) -> str:
    """Redis key for task-group resume envelope."""
    return f"{_TASKGROUP_PREFIX}{chat_id}:{task_key}"


class RedisCheckpointStore(CheckpointStore):
    """CheckpointStore implementation backed by async Redis."""

    def __init__(self, redis) -> None:
        self._redis = redis

    async def save_json(self, key: str, payload: dict[str, Any]) -> None:
        await self._redis.set(key, json.dumps(payload), ex=CHECKPOINT_TTL_SECONDS)

    async def load_json(self, key: str) -> dict[str, Any] | None:
        raw = await self._redis.get(key)
        if not raw:
            return None
        data = json.loads(raw)
        return data if isinstance(data, dict) else None

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)
