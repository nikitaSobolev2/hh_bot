from __future__ import annotations

import contextvars
import json
import time
from dataclasses import dataclass
from typing import Any

from src.core.logging import get_logger

logger = get_logger(__name__)

ENQUEUED_AT_HEADER = "x-hh-bot-enqueued-at-ms"
PUBLISHED_BYTES_HEADER = "x-hh-bot-payload-bytes"
LARGE_PAYLOAD_BYTES = 32 * 1024

_current_task_metrics: contextvars.ContextVar[TaskMetrics | None] = contextvars.ContextVar(
    "current_task_metrics",
    default=None,
)


@dataclass(slots=True)
class TaskMetrics:
    task_id: str
    task_name: str
    queue: str | None
    retries: int
    queue_wait_ms: int | None
    published_payload_bytes: int | None
    started_at_monotonic: float
    db_query_count: int = 0
    db_time_ms: float = 0.0
    redis_sync_clients: int = 0
    redis_async_clients: int = 0
    redis_sync_ops: int = 0
    redis_async_ops: int = 0
    redis_sync_time_ms: float = 0.0
    redis_async_time_ms: float = 0.0


def _safe_json_size(value: Any) -> int | None:
    try:
        return len(json.dumps(value, default=str).encode("utf-8"))
    except Exception:
        try:
            return len(repr(value).encode("utf-8", errors="replace"))
        except Exception:
            return None


def inject_publish_headers(headers: dict | None, body: Any) -> None:
    """Attach lightweight timing and payload metadata to task headers."""
    if headers is None:
        return
    headers.setdefault(ENQUEUED_AT_HEADER, int(time.time() * 1000))
    payload_bytes = _safe_json_size(body)
    if payload_bytes is None:
        return
    headers.setdefault(PUBLISHED_BYTES_HEADER, payload_bytes)
    if payload_bytes >= LARGE_PAYLOAD_BYTES:
        logger.info(
            "celery_task_large_publish_payload",
            payload_bytes=payload_bytes,
            task_name=headers.get("task"),
        )


def start_task_metrics(task: Any) -> None:
    request = getattr(task, "request", None)
    headers = getattr(request, "headers", None) or {}
    enqueued_at_ms = headers.get(ENQUEUED_AT_HEADER)
    queue_wait_ms: int | None = None
    if isinstance(enqueued_at_ms, (int, float)):
        queue_wait_ms = max(0, int(time.time() * 1000) - int(enqueued_at_ms))
    elif isinstance(enqueued_at_ms, str):
        try:
            queue_wait_ms = max(0, int(time.time() * 1000) - int(enqueued_at_ms))
        except ValueError:
            queue_wait_ms = None

    published_payload_bytes = headers.get(PUBLISHED_BYTES_HEADER)
    if isinstance(published_payload_bytes, str):
        try:
            published_payload_bytes = int(published_payload_bytes)
        except ValueError:
            published_payload_bytes = None
    elif not isinstance(published_payload_bytes, int):
        published_payload_bytes = None

    delivery_info = getattr(request, "delivery_info", None) or {}
    queue_name = None
    if isinstance(delivery_info, dict):
        queue_name = delivery_info.get("routing_key") or delivery_info.get("queue")

    metrics = TaskMetrics(
        task_id=str(getattr(request, "id", "") or ""),
        task_name=str(getattr(task, "name", "unknown") or "unknown"),
        queue=str(queue_name) if queue_name else None,
        retries=int(getattr(request, "retries", 0) or 0),
        queue_wait_ms=queue_wait_ms,
        published_payload_bytes=published_payload_bytes,
        started_at_monotonic=time.perf_counter(),
    )
    _current_task_metrics.set(metrics)

    logger.info(
        "celery_task_started_metrics",
        task_id=metrics.task_id,
        task_name=metrics.task_name,
        queue=metrics.queue,
        retries=metrics.retries,
        queue_wait_ms=metrics.queue_wait_ms,
        published_payload_bytes=metrics.published_payload_bytes,
    )


def finish_task_metrics(*, state: str | None, retval: Any) -> None:
    metrics = _current_task_metrics.get()
    if metrics is None:
        return

    runtime_ms = int((time.perf_counter() - metrics.started_at_monotonic) * 1000)
    result_bytes = _safe_json_size(retval)
    logger.info(
        "celery_task_finished_metrics",
        task_id=metrics.task_id,
        task_name=metrics.task_name,
        queue=metrics.queue,
        state=state,
        runtime_ms=runtime_ms,
        queue_wait_ms=metrics.queue_wait_ms,
        retries=metrics.retries,
        published_payload_bytes=metrics.published_payload_bytes,
        result_bytes=result_bytes,
        db_query_count=metrics.db_query_count,
        db_time_ms=round(metrics.db_time_ms, 3),
        redis_sync_clients=metrics.redis_sync_clients,
        redis_async_clients=metrics.redis_async_clients,
        redis_sync_ops=metrics.redis_sync_ops,
        redis_async_ops=metrics.redis_async_ops,
        redis_sync_time_ms=round(metrics.redis_sync_time_ms, 3),
        redis_async_time_ms=round(metrics.redis_async_time_ms, 3),
    )
    if result_bytes is not None and result_bytes >= LARGE_PAYLOAD_BYTES:
        logger.info(
            "celery_task_large_result_payload",
            task_id=metrics.task_id,
            task_name=metrics.task_name,
            result_bytes=result_bytes,
        )
    _current_task_metrics.set(None)


def record_db_query(elapsed_ms: float) -> None:
    metrics = _current_task_metrics.get()
    if metrics is None:
        return
    metrics.db_query_count += 1
    metrics.db_time_ms += float(elapsed_ms)


def record_redis_client(kind: str) -> None:
    metrics = _current_task_metrics.get()
    if metrics is None:
        return
    if kind == "async":
        metrics.redis_async_clients += 1
    else:
        metrics.redis_sync_clients += 1


def record_redis_command(kind: str, *, command: str, elapsed_ms: float) -> None:
    metrics = _current_task_metrics.get()
    if metrics is None:
        return
    if command in {"close", "aclose"}:
        return
    if kind == "async":
        metrics.redis_async_ops += 1
        metrics.redis_async_time_ms += float(elapsed_ms)
    else:
        metrics.redis_sync_ops += 1
        metrics.redis_sync_time_ms += float(elapsed_ms)
