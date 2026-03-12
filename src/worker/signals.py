"""Celery signal handlers for operational monitoring.

On task failure the full traceback is posted to the configured Telegram
log channel so issues are visible without tailing Docker logs.
"""

from __future__ import annotations

import contextlib
import html
import traceback

import httpx

from src.config import settings

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
_MAX_TB_LENGTH = 3500


def _send_telegram_message(text: str) -> None:
    """Fire-and-forget POST to the Telegram Bot API (sync, best-effort)."""
    chat_id = settings.log_telegram_chat_id
    if not chat_id or not settings.bot_token:
        return

    url = _TELEGRAM_API.format(token=settings.bot_token)
    with contextlib.suppress(Exception):
        httpx.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )


def _format_failure(
    task_id: str,
    task_name: str,
    args: tuple,
    kwargs: dict,
    exception: BaseException,
    tb: object,
) -> str:
    tb_text = "".join(traceback.format_tb(tb)) if tb else ""
    if len(tb_text) > _MAX_TB_LENGTH:
        tb_text = tb_text[-_MAX_TB_LENGTH:] + "\n… (truncated)"

    exc_repr = html.escape(repr(exception))
    tb_escaped = html.escape(tb_text)

    return (
        f"🔴 <b>Celery task failed</b>\n\n"
        f"<b>Task:</b> {html.escape(task_name)}\n"
        f"<b>ID:</b> <code>{html.escape(task_id)}</code>\n"
        f"<b>Args:</b> <code>{html.escape(repr(args))}</code>\n"
        f"<b>Kwargs:</b> <code>{html.escape(repr(kwargs))}</code>\n\n"
        f"<b>Exception:</b>\n<code>{exc_repr}</code>\n\n"
        f"<b>Traceback:</b>\n<pre>{tb_escaped}</pre>"
    )


def connect_signals(app) -> None:  # app: Celery
    """Attach all worker signal handlers to *app*."""
    from celery.signals import task_failure

    @task_failure.connect
    def on_task_failure(
        sender,
        task_id: str,
        exception: BaseException,
        traceback: object,
        einfo: object,
        args: tuple,
        kwargs: dict,
        **extra,
    ) -> None:
        task_name = getattr(sender, "name", "unknown") if sender else "unknown"
        message = _format_failure(task_id, task_name, args, kwargs, exception, traceback)
        _send_telegram_message(message)
