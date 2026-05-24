"""Redis state for the autorespond producer/consumer pipeline.

A single dispatcher seeds work units, a fan-out of ``cover_letter.pregenerate_for_apply``
fills letters into a Redis hash, and one ``autorespond.apply_pump`` consumes both.
Everything lives under the chat_id + task_key namespace so multiple users / runs
do not collide.

Why sync helpers
----------------
All callers (dispatcher async task, pregen sync-async hybrid, apply_pump Playwright
worker) need fast, blocking access to Redis. sync calls are micro-second cheap and
avoid event-loop juggling inside Celery tasks that already use ``run_async``.

Key lifetime
------------
Each helper sets ``_PIPELINE_TTL_S`` (24 h) so abandoned runs self-clean. The
``autorespond.recover_stalled`` beat task also clears state when the bar has
converged or run was cancelled.
"""

from __future__ import annotations

import json
import time
from typing import Any

from src.config import settings
from src.core.logging import get_logger
from src.core.redis import create_sync_redis

logger = get_logger(__name__)

_PIPELINE_TTL_S = 24 * 3600
_PIPELINE_ENVELOPE_KEY_PREFIX = "autorespond:pipeline:envelope:"


def _sync_redis():
    return create_sync_redis()


def ready_to_apply_key(chat_id: int, task_key: str) -> str:
    """ZSET: pending apply units. Member = JSON spec; score = ``-vacancy_id`` (newest first)."""
    return f"autorespond:pipeline:ready:{chat_id}:{task_key}"


def pregen_cache_key(chat_id: int, task_key: str) -> str:
    """HASH: pre-generated cover letters keyed by autoparsed_vacancy_id (str)."""
    return f"autorespond:pipeline:pregen:{chat_id}:{task_key}"


def pregen_pending_key(chat_id: int, task_key: str) -> str:
    """SET: vacancy ids whose pre-gen task is still in flight."""
    return f"autorespond:pipeline:pregen_pending:{chat_id}:{task_key}"


def pump_heartbeat_key(chat_id: int, task_key: str) -> str:
    """STR: unix timestamp written every few seconds by the active ``apply_pump``."""
    return f"autorespond:pipeline:pump_hb:{chat_id}:{task_key}"


def pipeline_envelope_key(chat_id: int, task_key: str) -> str:
    """STR JSON: kwargs needed to re-enqueue ``apply_pump`` from ``recover_stalled``."""
    return f"{_PIPELINE_ENVELOPE_KEY_PREFIX}{chat_id}:{task_key}"


# ---------------------------------------------------------------------------
# Envelope (recovery hint)
# ---------------------------------------------------------------------------


def save_pipeline_envelope(
    chat_id: int, task_key: str, envelope: dict[str, Any]
) -> None:
    r = _sync_redis()
    try:
        r.set(
            pipeline_envelope_key(chat_id, task_key),
            json.dumps(envelope),
            ex=_PIPELINE_TTL_S,
        )
    finally:
        r.close()


def load_pipeline_envelope(chat_id: int, task_key: str) -> dict[str, Any] | None:
    r = _sync_redis()
    try:
        raw = r.get(pipeline_envelope_key(chat_id, task_key))
        if not raw:
            return None
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    finally:
        r.close()


def clear_pipeline_envelope(chat_id: int, task_key: str) -> None:
    r = _sync_redis()
    try:
        r.delete(pipeline_envelope_key(chat_id, task_key))
    finally:
        r.close()


def iter_active_pipeline_envelopes() -> list[tuple[int, str]]:
    """SCAN envelope keys; return ``(chat_id, task_key)`` tuples for recovery sweep."""
    out: list[tuple[int, str]] = []
    r = _sync_redis()
    try:
        match = f"{_PIPELINE_ENVELOPE_KEY_PREFIX}*"
        for raw_key in r.scan_iter(match=match, count=100):
            key = raw_key if isinstance(raw_key, str) else raw_key.decode("utf-8")
            suffix = key[len(_PIPELINE_ENVELOPE_KEY_PREFIX) :]
            sep = suffix.find(":")
            if sep <= 0:
                continue
            try:
                chat_id = int(suffix[:sep])
            except ValueError:
                continue
            task_key = suffix[sep + 1 :]
            if task_key:
                out.append((chat_id, task_key))
    finally:
        r.close()
    return out


# ---------------------------------------------------------------------------
# Ready-to-apply ZSET
# ---------------------------------------------------------------------------


def seed_ready_to_apply(
    chat_id: int, task_key: str, items: list[dict[str, Any]]
) -> int:
    """Bulk-add apply specs to the ZSET. Returns the count added.

    ``score`` is ``-autoparsed_vacancy_id`` so ``ZPOPMIN`` returns newest IDs first
    (consistent with the old parent loop ordering).
    """
    if not items:
        return 0
    r = _sync_redis()
    key = ready_to_apply_key(chat_id, task_key)
    try:
        mapping: dict[str, float] = {}
        for spec in items:
            try:
                vid = int(spec["autoparsed_vacancy_id"])
            except (KeyError, TypeError, ValueError):
                continue
            mapping[json.dumps(spec, sort_keys=True)] = float(-vid)
        if not mapping:
            return 0
        pipe = r.pipeline()
        pipe.zadd(key, mapping)
        pipe.expire(key, _PIPELINE_TTL_S)
        results = pipe.execute()
        return int(results[0])
    finally:
        r.close()


def pop_ready_batch(
    chat_id: int, task_key: str, batch_size: int
) -> list[dict[str, Any]]:
    """ZPOPMIN up to ``batch_size`` specs. Empty when ZSET is empty."""
    if batch_size <= 0:
        return []
    r = _sync_redis()
    key = ready_to_apply_key(chat_id, task_key)
    try:
        popped = r.zpopmin(key, count=batch_size)
    finally:
        r.close()
    out: list[dict[str, Any]] = []
    for member, _score in popped or []:
        if isinstance(member, (bytes, bytearray)):
            member = member.decode("utf-8")
        try:
            spec = json.loads(member)
        except json.JSONDecodeError:
            continue
        if isinstance(spec, dict):
            out.append(spec)
    return out


def ready_remaining_count(chat_id: int, task_key: str) -> int:
    r = _sync_redis()
    try:
        return int(r.zcard(ready_to_apply_key(chat_id, task_key)) or 0)
    finally:
        r.close()


def clear_ready_to_apply(chat_id: int, task_key: str) -> None:
    r = _sync_redis()
    try:
        r.delete(ready_to_apply_key(chat_id, task_key))
    finally:
        r.close()


# ---------------------------------------------------------------------------
# Pregen cache + pending set
# ---------------------------------------------------------------------------


def mark_pregen_pending(chat_id: int, task_key: str, vacancy_ids: list[int]) -> None:
    if not vacancy_ids:
        return
    r = _sync_redis()
    key = pregen_pending_key(chat_id, task_key)
    try:
        pipe = r.pipeline()
        pipe.sadd(key, *[str(v) for v in vacancy_ids])
        pipe.expire(key, _PIPELINE_TTL_S)
        pipe.execute()
    finally:
        r.close()


def pregen_pending_count(chat_id: int, task_key: str) -> int:
    r = _sync_redis()
    try:
        return int(r.scard(pregen_pending_key(chat_id, task_key)) or 0)
    finally:
        r.close()


def store_pregen_letter(
    chat_id: int, task_key: str, vacancy_id: int, letter: str
) -> None:
    """Save cover letter (empty string allowed) and remove from pending in one transaction."""
    r = _sync_redis()
    cache_key = pregen_cache_key(chat_id, task_key)
    pending_key = pregen_pending_key(chat_id, task_key)
    ttl = int(settings.cover_letter_pregen_ttl_seconds)
    try:
        pipe = r.pipeline()
        pipe.hset(cache_key, str(vacancy_id), letter or "")
        pipe.expire(cache_key, ttl)
        pipe.srem(pending_key, str(vacancy_id))
        pipe.execute()
    finally:
        r.close()


def fetch_pregen_letter(
    chat_id: int, task_key: str, vacancy_id: int
) -> str | None:
    """Return cached letter; ``None`` when no entry exists.

    Empty string means the pre-gen task gave up (timeout / error) and the pump
    should apply without a letter (HH allows blank cover letters).
    """
    r = _sync_redis()
    try:
        val = r.hget(pregen_cache_key(chat_id, task_key), str(vacancy_id))
        if val is None:
            return None
        return val if isinstance(val, str) else val.decode("utf-8")
    finally:
        r.close()


def pregen_letter_exists(chat_id: int, task_key: str, vacancy_id: int) -> bool:
    r = _sync_redis()
    try:
        return bool(r.hexists(pregen_cache_key(chat_id, task_key), str(vacancy_id)))
    finally:
        r.close()


def clear_pregen_state(chat_id: int, task_key: str) -> None:
    r = _sync_redis()
    try:
        r.delete(
            pregen_cache_key(chat_id, task_key),
            pregen_pending_key(chat_id, task_key),
        )
    finally:
        r.close()


# ---------------------------------------------------------------------------
# Pump heartbeat
# ---------------------------------------------------------------------------


def touch_pump_heartbeat(chat_id: int, task_key: str) -> None:
    r = _sync_redis()
    try:
        r.set(
            pump_heartbeat_key(chat_id, task_key),
            str(int(time.time())),
            ex=_PIPELINE_TTL_S,
        )
    finally:
        r.close()


def pump_heartbeat_age_seconds(chat_id: int, task_key: str) -> float | None:
    r = _sync_redis()
    try:
        raw = r.get(pump_heartbeat_key(chat_id, task_key))
    finally:
        r.close()
    if raw is None:
        return None
    try:
        ts = float(raw)
    except (TypeError, ValueError):
        return None
    return max(0.0, time.time() - ts)


def clear_pump_heartbeat(chat_id: int, task_key: str) -> None:
    r = _sync_redis()
    try:
        r.delete(pump_heartbeat_key(chat_id, task_key))
    finally:
        r.close()


# ---------------------------------------------------------------------------
# Aggregate cleanup
# ---------------------------------------------------------------------------


def pipeline_has_pending_work(chat_id: int, task_key: str) -> bool:
    """True when a pipeline run still has ready units, in-flight pregen, or a saved envelope."""
    return (
        ready_remaining_count(chat_id, task_key) > 0
        or pregen_pending_count(chat_id, task_key) > 0
        or load_pipeline_envelope(chat_id, task_key) is not None
    )


def clear_all_pipeline_state(chat_id: int, task_key: str) -> None:
    """Wipe every key for a pipeline run (called after bar converges or cancel)."""
    r = _sync_redis()
    try:
        r.delete(
            ready_to_apply_key(chat_id, task_key),
            pregen_cache_key(chat_id, task_key),
            pregen_pending_key(chat_id, task_key),
            pump_heartbeat_key(chat_id, task_key),
            pipeline_envelope_key(chat_id, task_key),
        )
    finally:
        r.close()
