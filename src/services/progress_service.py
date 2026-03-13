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
"""

from __future__ import annotations

import asyncio
import contextlib
import json

from src.core.i18n import get_text
from src.core.logging import get_logger

logger = get_logger(__name__)

_BAR_WIDTH = 20
_THROTTLE_MS = 500
_PROGRESS_TTL = 4 * 3600  # seconds
_MSGLOCK_TTL = 10  # seconds


def render_bar(current: int, total: int) -> str:
    """Render a single progress bar: ``<code>██░░</code>  50%  5/10``."""
    pct = round(current / total * 100) if total else 0
    filled = round(_BAR_WIDTH * current / total) if total else 0
    blocks = "\u2588" * filled + "\u2591" * (_BAR_WIDTH - filled)
    return f"<code>{blocks}</code>  <b>{pct}%</b>  <i>{current}/{total}</i>"


def create_progress_redis():
    """Create an async Redis client suitable for ProgressService."""
    from src.core.redis import create_async_redis

    return create_async_redis()


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
    ) -> None:
        """Register a new task and show or update the pinned progress message."""
        state = {
            "title": title,
            "status": "running",
            "bars": [{"label": label, "current": 0, "total": 0} for label in bar_labels],
        }
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

    async def finish_task(self, task_key: str) -> None:
        """Mark task complete; send summary and clean up when all tasks are done."""
        raw = await self._redis.get(self._task_key(task_key))
        if raw:
            state = json.loads(raw)
            state["status"] = "completed"
            for bar in state["bars"]:
                if bar["total"] > 0:
                    bar["current"] = bar["total"]
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
        pin_msg_id = await self._get_or_create_pin_message(text)
        if pin_msg_id is None:
            return

        try:
            await self._bot.edit_message_text(
                text=text,
                chat_id=self._chat_id,
                message_id=pin_msg_id,
                parse_mode="HTML",
            )
        except TelegramBadRequest:
            # Message was deleted externally or text is unchanged — safe to ignore.
            pass
        except TelegramRetryAfter as exc:
            logger.warning("Progress edit flood control", retry_after=exc.retry_after)
            await asyncio.sleep(exc.retry_after)

    async def _get_or_create_pin_message(self, text: str) -> int | None:
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

    def _render_progress_text(self, tasks: dict[str, dict]) -> str:
        """Render the full combined progress message for all active tasks."""
        header = f"<b>{get_text('progress-title', self._locale)}</b>"
        sections = [self._render_task_section(state) for state in tasks.values()]
        return header + "\n\n" + "\n\n———\n\n".join(sections)

    def _render_task_section(self, state: dict) -> str:
        """Render a single task block: title, then each progress bar."""
        title = state["title"]
        is_done = state["status"] == "completed"
        done_mark = " ✅" if is_done else ""
        lines = [f"<b>📋</b> {title}{done_mark}"]
        for bar in state["bars"]:
            total = bar["total"]
            if total <= 0:
                continue
            lines.append(bar["label"])
            bar_line = render_bar(bar["current"], total)
            lines.append(f"{bar_line} ✅" if is_done else bar_line)
        return "\n".join(lines)

    def _render_summary(self, tasks: dict[str, dict]) -> str:
        """Render the all-done summary message sent after the pinned message is removed."""
        title = get_text("progress-completed-title", self._locale)
        task_lines = "\n".join(f"• {state['title']}" for state in tasks.values())
        return f"<b>{title}</b>\n\n{task_lines}"
