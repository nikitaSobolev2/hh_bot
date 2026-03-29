"""User-defined task group: ordered Celery steps (autoparse, autorespond, manual parsing)."""

from __future__ import annotations

import json
from typing import Any, Literal

import redis as sync_redis

from src.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

_TASK_GROUP_TTL_S = 365 * 24 * 3600

TaskGroupKind = Literal["autoparse", "autorespond", "parsing"]


def _task_group_key(telegram_id: int) -> str:
    return f"user:task_group:{telegram_id}"


def load_task_group_steps(telegram_id: int) -> list[dict[str, Any]]:
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        raw = r.get(_task_group_key(telegram_id))
        if not raw:
            return []
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        out: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            kind = item.get("kind")
            cid = item.get("company_id")
            if kind not in ("autoparse", "autorespond", "parsing"):
                continue
            try:
                cid_int = int(cid)
            except (TypeError, ValueError):
                continue
            out.append({"kind": kind, "company_id": cid_int})
        return out
    finally:
        r.close()


def save_task_group_steps(telegram_id: int, steps: list[dict[str, Any]]) -> None:
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        if not steps:
            r.delete(_task_group_key(telegram_id))
            return
        r.set(_task_group_key(telegram_id), json.dumps(steps), ex=_TASK_GROUP_TTL_S)
    finally:
        r.close()


def append_task_group_step(
    telegram_id: int, kind: TaskGroupKind, company_id: int
) -> None:
    steps = load_task_group_steps(telegram_id)
    steps.append({"kind": kind, "company_id": company_id})
    save_task_group_steps(telegram_id, steps)


def clear_task_group_steps(telegram_id: int) -> None:
    save_task_group_steps(telegram_id, [])


def remove_task_group_step_at(telegram_id: int, index: int) -> None:
    steps = load_task_group_steps(telegram_id)
    if 0 <= index < len(steps):
        del steps[index]
        save_task_group_steps(telegram_id, steps)
