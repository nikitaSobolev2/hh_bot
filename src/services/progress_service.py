"""Unified progress bar service for user task tracking via pinned Telegram messages.

Usage from Celery tasks
-----------------------
    redis = create_progress_redis()
    svc = ProgressService(bot, chat_id, redis, locale)
    await svc.start_task("parse:42", company.vacancy_title, [scraping_label, keywords_label])
    # ... during work ...
    await svc.update_bar("parse:42", bar_index=0, current=5, total=50)
    # ... on completion ...
    await svc.finish_task("parse:42")

Multiple concurrent tasks for the same chat_id each manage their own Redis key.
They all edit the same pinned message so the user sees one combined progress view.

Pinning is only performed in private chats (chat_id > 0).
When all registered tasks complete the pinned message is deleted and a compact
completion summary is sent in its place.

Redis keys (all with 4-hour TTL)
---------------------------------
    progress:task:{chat_id}:{task_key}  — per-task JSON state
    progress:pin:{chat_id}             — pinned message ID
    progress:msglock:{chat_id}         — short lock for create/delete ops (10 s)
    progress:throttle:{chat_id}        — 500 ms throttle gate
    progress:shortcb:{chat_id}:{token} — maps 16-char hex token to full task_key when
                                         callback_data would exceed 64 bytes (same TTL)
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
from html import escape
import json

from src.core.celery_async import normalize_celery_task_id
from src.core.i18n import get_text
from src.core.logging import get_logger
from src.services.progress_cancel import clear_user_cancelled_sync

logger = get_logger(__name__)

_BAR_WIDTH = 20
# Inline keyboard callback_data (Telegram max 64 bytes per button).
PROGRESS_CANCEL_PREFIX = "prog:cancel:"
PROGRESS_TITLE_PREFIX = "prog:t:"
PROGRESS_REFRESH_PREFIX = "prog:r:"
PROGRESS_TITLE_SHORT_PREFIX = "prog:t!"
PROGRESS_REFRESH_SHORT_PREFIX = "prog:r!"
PROGRESS_CANCEL_SHORT_PREFIX = "prog:x!"
_TELEGRAM_CALLBACK_DATA_MAX_BYTES = 64
_MAX_TITLE_IN_BUTTON = 40
_THROTTLE_MS = 500
_PROGRESS_TTL = 4 * 3600  # seconds
_MSGLOCK_TTL = 10  # seconds


def short_callback_storage_key(chat_id: int, token: str) -> str:
    """Redis key for resolving short inline callback tokens to full ``task_key``."""
    return f"progress:shortcb:{chat_id}:{token}"


def task_key_fits_callback_data(task_key: str) -> bool:
    """True if ``task_key`` fits Telegram's 64-byte limit for all progress inline buttons."""
    enc = task_key.replace(":", "_")
    lim = _TELEGRAM_CALLBACK_DATA_MAX_BYTES
    return (
        len((PROGRESS_TITLE_PREFIX + enc).encode("utf-8")) <= lim
        and len((PROGRESS_REFRESH_PREFIX + enc).encode("utf-8")) <= lim
        and len((PROGRESS_CANCEL_PREFIX + enc).encode("utf-8")) <= lim
    )


def render_bar(current: int, total: int) -> str:
    """Render a single progress bar: ``<code>██░░</code>  50%  5/10``."""
    if total <= 0:
        pct = 0
        filled = 0
        display_current = 0
    else:
        display_current = min(current, total)  # Cap at 100% when goal < actual work
        pct = round(display_current / total * 100)
        filled = round(_BAR_WIDTH * display_current / total)
    blocks = "\u2588" * filled + "\u2591" * (_BAR_WIDTH - filled)
    return f"<code>{blocks}</code>  <b>{pct}%</b>  <i>{display_current}/{total}</i>"


def render_indeterminate_progress(locale: str) -> str:
    """Render a textual loader for phases whose total is not known yet."""
    return get_text("progress-processing", locale)


def create_progress_redis():
    """Create an async Redis client suitable for ProgressService."""
    from src.core.redis import create_async_redis

    return create_async_redis()


def _telegram_edit_failed_because_message_gone(exc: BaseException) -> bool:
    """True when edit fails because the message was deleted or id is invalid."""
    s = str(exc).lower()
    return any(
        x in s
        for x in (
            "message to edit not found",
            "message_id_invalid",
            "message not found",
            "bad request: message to edit not found",
        )
    )


def _telegram_edit_unchanged(exc: BaseException) -> bool:
    """True when Telegram rejects edit because body is identical to current."""
    s = str(exc).lower()
    return "message is not modified" in s or "message_not_modified" in s


async def _scan_progress_task_chat_ids(redis) -> set[int]:
    """Collect distinct chat IDs from ``progress:task:{chat_id}:...`` keys (SCAN, not KEYS)."""
    chat_ids: set[int] = set()
    cursor = 0
    while True:
        cursor, keys = await redis.scan(cursor, match="progress:task:*", count=256)
        for raw in keys:
            key = raw.decode() if isinstance(raw, bytes) else raw
            parts = key.split(":", 3)
            if len(parts) >= 4 and parts[0] == "progress" and parts[1] == "task":
                with contextlib.suppress(ValueError):
                    chat_ids.add(int(parts[2]))
        if cursor == 0:
            break
    return chat_ids


async def _scan_progress_pin_chat_ids(redis) -> set[int]:
    """Collect distinct chat IDs from ``progress:pin:{chat_id}`` keys (SCAN, not KEYS)."""
    chat_ids: set[int] = set()
    cursor = 0
    while True:
        cursor, keys = await redis.scan(cursor, match="progress:pin:*", count=256)
        for raw in keys:
            key = raw.decode() if isinstance(raw, bytes) else raw
            parts = key.split(":", 2)
            if len(parts) >= 3 and parts[0] == "progress" and parts[1] == "pin":
                with contextlib.suppress(ValueError):
                    chat_ids.add(int(parts[2]))
        if cursor == 0:
            break
    return chat_ids


async def scan_progress_namespace_chat_ids(redis) -> set[int]:
    """Distinct chat IDs referenced by ``progress:task:*`` or ``progress:pin:*`` Redis keys."""
    task_ids = await _scan_progress_task_chat_ids(redis)
    pin_ids = await _scan_progress_pin_chat_ids(redis)
    return task_ids | pin_ids


async def refresh_progress_pins_for_active_chats(bot, *, default_locale: str = "ru") -> int:
    """After bot restart: re-post or refresh pinned progress for chats with task state in Redis.

    Ensures users see the combined progress message again if Telegram messages were lost
    or if edits had failed silently before the restart.
    """
    redis = create_progress_redis()
    try:
        chat_ids = await _scan_progress_task_chat_ids(redis)
        n = 0
        for chat_id in sorted(chat_ids):
            svc = ProgressService(bot, chat_id, redis, default_locale)
            tasks = await svc._load_all_tasks()
            if not tasks:
                continue
            await svc._refresh_message(force=True)
            n += 1
        if n:
            logger.info("progress_pins_refreshed_after_restart", chats=n)
        return n
    finally:
        await redis.aclose()


class ProgressService:
    """Manages user progress bars as a single pinned message in DM chats.

    Multiple concurrent background tasks for the same ``chat_id`` each call
    ``start_task`` / ``update_bar`` / ``finish_task``.  The service coordinates
    them through Redis so they all appear in one message.
    """

    def __init__(
        self,
        bot,
        chat_id: int,
        redis,
        locale: str = "ru",
    ) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._redis = redis
        self._locale = locale

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_task(
        self,
        task_key: str,
        title: str,
        bar_labels: list[str],
        celery_task_id: str | None = None,
        initial_totals: list[int] | None = None,
        *,
        steps: list[dict[str, str]] | None = None,
        active_step_index: int | None = None,
        group: dict[str, str | int] | None = None,
    ) -> None:
        """Register a new task and show or update the pinned progress message."""
        bars = []
        for i, label in enumerate(bar_labels):
            total = initial_totals[i] if initial_totals and i < len(initial_totals) else 0
            bars.append({"label": label, "current": 0, "total": total})
        state = {
            "title": title,
            "status": "running",
            "bars": bars,
        }
        if steps is not None:
            state["steps"] = list(steps)
        if active_step_index is not None:
            state["active_step_index"] = active_step_index
        if group is not None:
            state["group"] = dict(group)
        with contextlib.suppress(Exception):
            clear_user_cancelled_sync(self._chat_id, task_key)
        if celery_task_id is not None:
            nid = normalize_celery_task_id(celery_task_id)
            if nid:
                state["celery_task_id"] = nid
        await self._redis.set(
            self._task_key(task_key),
            json.dumps(state),
            ex=_PROGRESS_TTL,
        )
        try:
            await self._refresh_message(force=True)
        except Exception:
            await self._redis.delete(self._task_key(task_key))
            raise

    async def set_steps(
        self,
        task_key: str,
        steps: list[dict[str, str]],
        *,
        active_index: int | None = None,
    ) -> None:
        """Set ordered pipeline steps: each item ``{id, label, state}`` where state is
        ``pending``, ``running``, ``done``, or ``skipped``."""
        raw = await self._redis.get(self._task_key(task_key))
        if not raw:
            return
        state = json.loads(raw)
        state["steps"] = list(steps)
        if active_index is not None:
            state["active_step_index"] = active_index
        await self._redis.set(
            self._task_key(task_key),
            json.dumps(state),
            ex=_PROGRESS_TTL,
        )
        await self._refresh_message(force=True)

    async def set_active_step_index(self, task_key: str, index: int) -> None:
        raw = await self._redis.get(self._task_key(task_key))
        if not raw:
            return
        state = json.loads(raw)
        state["active_step_index"] = index
        await self._redis.set(
            self._task_key(task_key),
            json.dumps(state),
            ex=_PROGRESS_TTL,
        )
        await self._refresh_message(force=False)

    async def set_step_state(self, task_key: str, step_id: str, new_state: str) -> None:
        raw = await self._redis.get(self._task_key(task_key))
        if not raw:
            return
        state = json.loads(raw)
        steps = state.get("steps") or []
        for s in steps:
            if s.get("id") == step_id:
                s["state"] = new_state
                break
        state["steps"] = steps
        await self._redis.set(
            self._task_key(task_key),
            json.dumps(state),
            ex=_PROGRESS_TTL,
        )
        await self._refresh_message(force=False)

    async def set_group(
        self,
        task_key: str,
        *,
        current: int,
        total: int,
        label: str = "",
    ) -> None:
        """Outer counter for task-group runs: e.g. step 2 of 5 in a batch."""
        raw = await self._redis.get(self._task_key(task_key))
        if not raw:
            return
        state = json.loads(raw)
        state["group"] = {"current": current, "total": total, "label": label}
        await self._redis.set(
            self._task_key(task_key),
            json.dumps(state),
            ex=_PROGRESS_TTL,
        )
        await self._refresh_message(force=False)

    async def set_nested_steps(
        self,
        task_key: str,
        steps: list[dict[str, str]],
        *,
        active_index: int | None = None,
    ) -> None:
        """Sub-steps for the current macro step (e.g. autorespond inside a task group)."""
        raw = await self._redis.get(self._task_key(task_key))
        if not raw:
            return
        state = json.loads(raw)
        state["nested_steps"] = list(steps)
        if active_index is not None:
            state["nested_active_step_index"] = active_index
        else:
            state.pop("nested_active_step_index", None)
        bars = state.get("bars") or []
        if len(bars) > 1:
            active_label = self._resolve_active_step_label(
                state["nested_steps"],
                state.get("nested_active_step_index"),
            )
            bars[1]["label"] = active_label or get_text(
                "progress-taskgroup-detail-bar",
                self._locale,
            )
        state["bars"] = bars
        await self._redis.set(
            self._task_key(task_key),
            json.dumps(state),
            ex=_PROGRESS_TTL,
        )
        await self._refresh_message(force=True)

    async def set_nested_step_state(self, task_key: str, step_id: str, new_state: str) -> None:
        raw = await self._redis.get(self._task_key(task_key))
        if not raw:
            return
        state = json.loads(raw)
        nested = state.get("nested_steps") or []
        for s in nested:
            if s.get("id") == step_id:
                s["state"] = new_state
                break
        state["nested_steps"] = nested
        bars = state.get("bars") or []
        if len(bars) > 1:
            active_label = self._resolve_active_step_label(
                nested,
                state.get("nested_active_step_index"),
            )
            bars[1]["label"] = active_label or get_text(
                "progress-taskgroup-detail-bar",
                self._locale,
            )
        state["bars"] = bars
        await self._redis.set(
            self._task_key(task_key),
            json.dumps(state),
            ex=_PROGRESS_TTL,
        )
        await self._refresh_message(force=False)

    async def set_nested_active_step_index(self, task_key: str, index: int) -> None:
        raw = await self._redis.get(self._task_key(task_key))
        if not raw:
            return
        state = json.loads(raw)
        state["nested_active_step_index"] = index
        bars = state.get("bars") or []
        nested = state.get("nested_steps") or []
        if len(bars) > 1:
            active_label = self._resolve_active_step_label(nested, index)
            bars[1]["label"] = active_label or get_text(
                "progress-taskgroup-detail-bar",
                self._locale,
            )
        state["bars"] = bars
        await self._redis.set(
            self._task_key(task_key),
            json.dumps(state),
            ex=_PROGRESS_TTL,
        )
        await self._refresh_message(force=False)

    async def clear_nested_steps(self, task_key: str) -> None:
        """Remove nested sub-steps and reset the detail bar (index 1) if present."""
        raw = await self._redis.get(self._task_key(task_key))
        if not raw:
            return
        state = json.loads(raw)
        state.pop("nested_steps", None)
        state.pop("nested_active_step_index", None)
        bars = state.get("bars") or []
        if len(bars) > 1:
            bars[1]["label"] = get_text("progress-taskgroup-detail-bar", self._locale)
            bars[1]["current"] = 0
            bars[1]["total"] = 0
        state["bars"] = bars
        await self._redis.set(
            self._task_key(task_key),
            json.dumps(state),
            ex=_PROGRESS_TTL,
        )
        await self._refresh_message(force=False)

    async def update_child_celery_task_id(
        self, task_key: str, child_celery_task_id: str | None
    ) -> None:
        """Store a spawned child Celery task id (orchestrator dispatches sub-tasks)."""
        raw = await self._redis.get(self._task_key(task_key))
        if not raw:
            return
        state = json.loads(raw)
        if child_celery_task_id is not None:
            nid = normalize_celery_task_id(child_celery_task_id)
            if nid:
                state["child_celery_task_id"] = nid
            else:
                state.pop("child_celery_task_id", None)
        else:
            state.pop("child_celery_task_id", None)
        await self._redis.set(
            self._task_key(task_key),
            json.dumps(state),
            ex=_PROGRESS_TTL,
        )
        await self._refresh_message(force=True)

    async def update_bar(
        self,
        task_key: str,
        bar_index: int,
        current: int,
        total: int,
    ) -> None:
        """Update a progress bar for the given task (throttled, monotonic)."""
        raw = await self._redis.get(self._task_key(task_key))
        if not raw:
            return
        state = json.loads(raw)
        bars = state["bars"]
        if bar_index < len(bars):
            bar = bars[bar_index]
            if current > bar["current"]:
                bar["current"] = current
            bar["total"] = total
        await self._redis.set(
            self._task_key(task_key),
            json.dumps(state),
            ex=_PROGRESS_TTL,
        )
        await self._refresh_message(force=False)

    async def set_bar_label(self, task_key: str, bar_index: int, label: str) -> None:
        """Update a progress bar label without changing its counters."""
        raw = await self._redis.get(self._task_key(task_key))
        if not raw:
            return
        state = json.loads(raw)
        bars = state.get("bars") or []
        if 0 <= bar_index < len(bars):
            bars[bar_index]["label"] = label
        state["bars"] = bars
        await self._redis.set(
            self._task_key(task_key),
            json.dumps(state),
            ex=_PROGRESS_TTL,
        )
        await self._refresh_message(force=False)

    async def update_celery_task_id(self, task_key: str, celery_task_id: str | None) -> None:
        """Update stored Celery task id (e.g. after re-dispatching a child batch task)."""
        raw = await self._redis.get(self._task_key(task_key))
        if not raw:
            return
        state = json.loads(raw)
        if celery_task_id is not None:
            nid = normalize_celery_task_id(celery_task_id)
            if nid:
                state["celery_task_id"] = nid
            else:
                state.pop("celery_task_id", None)
        else:
            state.pop("celery_task_id", None)
        await self._redis.set(
            self._task_key(task_key),
            json.dumps(state),
            ex=_PROGRESS_TTL,
        )
        await self._refresh_message(force=True)

    async def update_footer(self, task_key: str, lines: list[str]) -> None:
        """Update optional footer lines shown under the task title (e.g. failure counts)."""
        raw = await self._redis.get(self._task_key(task_key))
        if not raw:
            return
        state = json.loads(raw)
        state["footer_lines"] = lines
        await self._redis.set(
            self._task_key(task_key),
            json.dumps(state),
            ex=_PROGRESS_TTL,
        )
        await self._refresh_message(force=False)

    async def update_completion_summary(self, task_key: str, lines: list[str]) -> None:
        """Store custom lines for final completion summary after pinned progress is removed."""
        raw = await self._redis.get(self._task_key(task_key))
        if not raw:
            return
        state = json.loads(raw)
        state["completion_summary_lines"] = list(lines)
        await self._redis.set(
            self._task_key(task_key),
            json.dumps(state),
            ex=_PROGRESS_TTL,
        )
        await self._refresh_message(force=False)

    async def mark_retrying(self, task_key: str) -> None:
        """Mark task as retrying after an error. Shows retry message in the UI."""
        raw = await self._redis.get(self._task_key(task_key))
        if raw:
            state = json.loads(raw)
            state["status"] = "retrying"
            await self._redis.set(
                self._task_key(task_key),
                json.dumps(state),
                ex=_PROGRESS_TTL,
            )
            await self._refresh_message(force=True)

    async def cancel_task(self, task_key: str) -> None:
        """Remove task from progress and refresh. Call after revoking the Celery task."""
        await self._redis.delete(self._task_key(task_key))
        tasks = await self._load_all_tasks()
        if not tasks:
            await self._cleanup_pin_only()
        else:
            await self._refresh_message(force=True)

    async def finish_task(
        self,
        task_key: str,
        shortage_note: str | None = None,
        *,
        complete_bars: bool = True,
    ) -> None:
        """Mark task complete; send summary and clean up when all tasks are done."""
        raw = await self._redis.get(self._task_key(task_key))
        if raw:
            state = json.loads(raw)
            state["status"] = "completed"
            if complete_bars:
                for bar in state["bars"]:
                    if bar["total"] > 0:
                        bar["current"] = bar["total"]
            for s in state.get("steps") or []:
                if s.get("state") != "skipped":
                    s["state"] = "done"
            if shortage_note:
                state["note"] = shortage_note
            await self._redis.set(
                self._task_key(task_key),
                json.dumps(state),
                ex=_PROGRESS_TTL,
            )

        await self._refresh_message(force=True)

        tasks = await self._load_all_tasks()
        all_done = bool(tasks) and all(t["status"] == "completed" for t in tasks.values())
        if all_done:
            await self._finalise(tasks)

    # ------------------------------------------------------------------
    # Redis key helpers
    # ------------------------------------------------------------------

    def _task_key(self, task_key: str) -> str:
        return f"progress:task:{self._chat_id}:{task_key}"

    def _pin_key(self) -> str:
        return f"progress:pin:{self._chat_id}"

    def _msglock_key(self) -> str:
        return f"progress:msglock:{self._chat_id}"

    def _throttle_key(self) -> str:
        return f"progress:throttle:{self._chat_id}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _is_dm(self) -> bool:
        return self._chat_id > 0

    async def _load_all_tasks(self) -> dict[str, dict]:
        """Load all active task states for this chat from Redis."""
        keys = await self._redis.keys(f"progress:task:{self._chat_id}:*")
        if not keys:
            return {}
        values = await self._redis.mget(*keys)
        result: dict[str, dict] = {}
        for key, raw in zip(keys, values, strict=True):
            if not raw:
                continue
            suffix = key.split(":", 3)[-1]
            with contextlib.suppress(Exception):
                result[suffix] = json.loads(raw)
        return result

    async def _ensure_short_callback_tokens(self, tasks: dict[str, dict]) -> dict[str, str]:
        """Map ``task_key`` -> 16-char hex token when full callback_data would exceed 64 bytes."""
        out: dict[str, str] = {}
        for task_key, state in tasks.items():
            if state.get("status") == "completed":
                continue
            if task_key_fits_callback_data(task_key):
                continue
            token = hashlib.sha256(f"{self._chat_id}:{task_key}".encode()).hexdigest()[:16]
            await self._redis.set(
                short_callback_storage_key(self._chat_id, token),
                task_key,
                ex=_PROGRESS_TTL,
            )
            out[task_key] = token
        return out

    async def _refresh_message(self, *, force: bool) -> None:
        """Edit the pinned message (or create it if absent), throttled unless forced."""
        from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

        if not force:
            acquired = await self._redis.set(self._throttle_key(), "1", nx=True, px=_THROTTLE_MS)
            if not acquired:
                return

        tasks = await self._load_all_tasks()
        if not tasks:
            return

        text = self._render_progress_text(tasks)
        short_tokens = await self._ensure_short_callback_tokens(tasks)
        reply_markup = self._build_cancel_keyboard(tasks, short_tokens)
        pin_msg_id = await self._get_or_create_pin_message(text, reply_markup)
        if pin_msg_id is None:
            return

        try:
            await self._bot.edit_message_text(
                text=text,
                chat_id=self._chat_id,
                message_id=pin_msg_id,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        except TelegramBadRequest as exc:
            if _telegram_edit_unchanged(exc):
                return
            if _telegram_edit_failed_because_message_gone(exc):
                logger.info(
                    "progress_pin_message_gone_recreating",
                    chat_id=self._chat_id,
                    detail=str(exc)[:300],
                )
                await self._redis.delete(self._pin_key())
                await self._get_or_create_pin_message(text, reply_markup)
            else:
                logger.warning(
                    "progress_message_edit_failed",
                    chat_id=self._chat_id,
                    detail=str(exc)[:300],
                )
        except TelegramRetryAfter as exc:
            logger.warning("Progress edit flood control", retry_after=exc.retry_after)
            await asyncio.sleep(exc.retry_after)

    async def _get_or_create_pin_message(
        self, text: str, reply_markup=None
    ) -> int | None:
        """Return the pinned message ID, creating and pinning it if it does not exist."""
        from aiogram.exceptions import TelegramBadRequest

        pin_raw = await self._redis.get(self._pin_key())
        if pin_raw:
            return int(pin_raw)

        # Short Redis lock prevents two workers from racing to create the message.
        acquired = await self._redis.set(self._msglock_key(), "1", nx=True, ex=_MSGLOCK_TTL)
        if not acquired:
            await asyncio.sleep(0.3)
            pin_raw = await self._redis.get(self._pin_key())
            return int(pin_raw) if pin_raw else None

        try:
            msg = await self._bot.send_message(
                chat_id=self._chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            msg_id = msg.message_id
            await self._redis.set(self._pin_key(), str(msg_id), ex=_PROGRESS_TTL)
            if self._is_dm:
                with contextlib.suppress(TelegramBadRequest):
                    await self._bot.pin_chat_message(
                        chat_id=self._chat_id,
                        message_id=msg_id,
                        disable_notification=True,
                    )
            return msg_id
        finally:
            await self._redis.delete(self._msglock_key())

    async def _cleanup_pin_only(self) -> None:
        """Remove pinned message and task keys without sending completion summary."""
        from aiogram.exceptions import TelegramBadRequest

        pin_raw = await self._redis.get(self._pin_key())
        if pin_raw:
            pin_msg_id = int(pin_raw)
            if self._is_dm:
                with contextlib.suppress(TelegramBadRequest):
                    await self._bot.unpin_chat_message(
                        chat_id=self._chat_id,
                        message_id=pin_msg_id,
                    )
            with contextlib.suppress(TelegramBadRequest):
                await self._bot.delete_message(
                    chat_id=self._chat_id,
                    message_id=pin_msg_id,
                )
            await self._redis.delete(self._pin_key())

        task_keys = await self._redis.keys(f"progress:task:{self._chat_id}:*")
        if task_keys:
            await self._redis.delete(*task_keys)

    async def _finalise(self, tasks: dict[str, dict]) -> None:
        """Unpin and delete the progress message, then send a completion summary."""
        from aiogram.exceptions import TelegramBadRequest

        pin_raw = await self._redis.get(self._pin_key())
        if pin_raw:
            pin_msg_id = int(pin_raw)
            if self._is_dm:
                with contextlib.suppress(TelegramBadRequest):
                    await self._bot.unpin_chat_message(
                        chat_id=self._chat_id,
                        message_id=pin_msg_id,
                    )
            with contextlib.suppress(TelegramBadRequest):
                await self._bot.delete_message(
                    chat_id=self._chat_id,
                    message_id=pin_msg_id,
                )
            await self._redis.delete(self._pin_key())

        task_keys = await self._redis.keys(f"progress:task:{self._chat_id}:*")
        if task_keys:
            await self._redis.delete(*task_keys)

        with contextlib.suppress(TelegramBadRequest):
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=self._render_summary(tasks),
                parse_mode="HTML",
            )

    # ------------------------------------------------------------------
    # Text renderers
    # ------------------------------------------------------------------

    def _build_cancel_keyboard(
        self, tasks: dict[str, dict], short_tokens: dict[str, str] | None = None
    ):
        """Inline keyboard: title (noop), try refresh, cancel per running task."""
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        short_tokens = short_tokens or {}
        buttons = []
        sorted_items = sorted(tasks.items())
        for idx, (task_key, state) in enumerate(sorted_items, start=1):
            if state.get("status") == "completed":
                continue
            title = state.get("title", "") or get_text(
                "progress-btn-task-title-fallback", self._locale
            )
            btn_title = title
            if len(btn_title) > _MAX_TITLE_IN_BUTTON:
                btn_title = btn_title[: _MAX_TITLE_IN_BUTTON - 1] + "…"
            if task_key in short_tokens:
                tok = short_tokens[task_key]
                cd_title = f"{PROGRESS_TITLE_SHORT_PREFIX}{tok}"
                cd_refresh = f"{PROGRESS_REFRESH_SHORT_PREFIX}{tok}"
                cd_cancel = f"{PROGRESS_CANCEL_SHORT_PREFIX}{tok}"
            else:
                encoded_key = task_key.replace(":", "_")
                cd_title = f"{PROGRESS_TITLE_PREFIX}{encoded_key}"
                cd_refresh = f"{PROGRESS_REFRESH_PREFIX}{encoded_key}"
                cd_cancel = f"{PROGRESS_CANCEL_PREFIX}{encoded_key}"
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"{idx}. {btn_title}",
                        callback_data=cd_title,
                    ),
                    InlineKeyboardButton(
                        text=get_text("progress-btn-try-refresh", self._locale),
                        callback_data=cd_refresh,
                    ),
                    InlineKeyboardButton(
                        text=get_text("progress-btn-cancel-inline", self._locale),
                        callback_data=cd_cancel,
                    ),
                ]
            )
        if not buttons:
            return None
        return InlineKeyboardMarkup(inline_keyboard=buttons)

    def _render_progress_text(self, tasks: dict[str, dict]) -> str:
        """Render the full combined progress message for all active tasks."""
        header = f"<b>{get_text('progress-title', self._locale)}</b>"
        sorted_items = sorted(tasks.items())
        sections = [
            self._render_task_section(state, task_number=idx)
            for idx, (_, state) in enumerate(sorted_items, start=1)
        ]
        return header + "\n\n" + "\n\n———\n\n".join(sections)

    def _render_task_section(self, state: dict, task_number: int = 1) -> str:
        """Render a single task block: number and title, optional group/steps, then bars."""
        title = self._escape_html(state["title"])
        status = state.get("status", "running")
        is_done = status == "completed"
        is_retrying = status == "retrying"
        done_mark = " ✅" if is_done else ""
        lines = [f"<b>📋</b> {task_number}. {title}{done_mark}"]
        if is_retrying:
            lines.append(get_text("progress-retrying", self._locale))
        grp = state.get("group")
        if isinstance(grp, dict) and grp.get("total", 0) > 0:
            gc = int(grp.get("current") or 0)
            gt = int(grp.get("total") or 0)
            glabel = self._escape_html((grp.get("label") or "").strip())
            part2 = f" — {glabel}" if glabel else ""
            lines.append(
                get_text(
                    "progress-group-line",
                    self._locale,
                    current=gc,
                    total=gt,
                    part2=part2,
                )
            )
        lines.extend(self._render_steps_lines(state, is_done))
        if state.get("nested_steps"):
            lines.append("")
            lines.append(
                f"<i>{get_text('progress-taskgroup-nested-header', self._locale)}</i>"
            )
            lines.extend(self._render_nested_steps_lines(state, is_done))
        if state.get("footer_lines"):
            lines.extend(self._escape_html(line) for line in state["footer_lines"])
        if is_done and state.get("note"):
            lines.append(self._escape_html(state["note"]))
        for bar in state["bars"]:
            total = bar["total"]
            if total <= 0:
                continue
            lines.append(self._escape_html(bar["label"]))
            if not is_done and total == 1 and bar["current"] <= 0:
                bar_line = self._escape_html(render_indeterminate_progress(self._locale))
            else:
                bar_line = render_bar(bar["current"], total)
            lines.append(f"{bar_line} ✅" if is_done else bar_line)
        return "\n".join(lines)

    def _render_steps_lines(self, state: dict, is_done: bool) -> list[str]:
        """Render pipeline step indicators (compact list + active hint)."""
        steps = state.get("steps")
        if not steps:
            return []
        out: list[str] = []
        n = len(steps)
        active_i = state.get("active_step_index")
        if active_i is None and not is_done:
            for i, s in enumerate(steps):
                if s.get("state") == "running":
                    active_i = i
                    break
            if active_i is None:
                for i, s in enumerate(steps):
                    if s.get("state") == "pending":
                        active_i = i
                        break
        for i, s in enumerate(steps):
            st = s.get("state") or "pending"
            label = self._escape_html(s.get("label") or s.get("id") or "?")
            if st == "done" or (is_done and st != "skipped"):
                mark = "✓"
            elif st == "skipped":
                mark = "·"
            elif st == "running" or (active_i is not None and i == active_i):
                mark = "→"
            else:
                mark = "○"
            out.append(f"{mark} <i>{i + 1}/{n}</i> {label}")
        return out

    def _render_nested_steps_lines(self, state: dict, is_done: bool) -> list[str]:
        """Sub-steps for the current macro step (task group + nested autorespond pipeline)."""
        steps = state.get("nested_steps")
        if not steps:
            return []
        out: list[str] = []
        n = len(steps)
        active_i = state.get("nested_active_step_index")
        if active_i is None and not is_done:
            for i, s in enumerate(steps):
                if s.get("state") == "running":
                    active_i = i
                    break
            if active_i is None:
                for i, s in enumerate(steps):
                    if s.get("state") == "pending":
                        active_i = i
                        break
        for i, s in enumerate(steps):
            st = s.get("state") or "pending"
            label = self._escape_html(s.get("label") or s.get("id") or "?")
            if st == "done" or (is_done and st != "skipped"):
                mark = "✓"
            elif st == "skipped":
                mark = "·"
            elif st == "running" or (active_i is not None and i == active_i):
                mark = "→"
            else:
                mark = "○"
            out.append(f"{mark} <i>{i + 1}/{n}</i> {label}")
        return out

    def _render_summary(self, tasks: dict[str, dict]) -> str:
        """Render the all-done summary message sent after the pinned message is removed."""
        title = get_text("progress-completed-title", self._locale)
        sections: list[str] = []
        for state in tasks.values():
            heading = self._escape_html(state["title"])
            summary_lines = state.get("completion_summary_lines") or []
            if summary_lines:
                lines = [f"<b>{heading}</b>"]
                lines.extend(self._escape_html(line) for line in summary_lines)
                sections.append("\n".join(lines))
            else:
                sections.append(f"• {heading}")
        return f"<b>{title}</b>\n\n" + "\n\n".join(sections)

    @staticmethod
    def _escape_html(value: object) -> str:
        """Escape dynamic text before embedding it into Telegram HTML."""
        return escape(str(value), quote=False)

    @staticmethod
    def _resolve_active_step_label(
        steps: list[dict],
        active_index: int | None,
    ) -> str | None:
        """Return label of current running/pending step for nested detail bar."""
        if not steps:
            return None
        if active_index is not None and 0 <= active_index < len(steps):
            label = steps[active_index].get("label")
            if isinstance(label, str) and label:
                return label
        for state_name in ("running", "pending"):
            for step in steps:
                if step.get("state") == state_name:
                    label = step.get("label")
                    if isinstance(label, str) and label:
                        return label
        return None
