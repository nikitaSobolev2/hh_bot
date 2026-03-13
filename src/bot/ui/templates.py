"""Message template builders for consistent formatting across all modules.

Every user-facing message in the bot should be constructed using these helpers
to guarantee a uniform visual structure:

    <b>Title</b>
    ─────────────
    Body text here

    Footer / hint text

Usage
-----
    from src.bot.ui.templates import MessageTemplate

    text = (
        MessageTemplate("parsing-title", i18n)
        .body("parsing-body", count=str(count))
        .build()
    )
"""

from __future__ import annotations

from src.core.constants import TELEGRAM_SAFE_LIMIT
from src.core.i18n import I18nContext

_DIVIDER = "─" * 20


class MessageTemplate:
    """Fluent builder for structured Telegram HTML messages."""

    def __init__(self, title_key: str, i18n: I18nContext) -> None:
        self._title = i18n.get(title_key)
        self._i18n = i18n
        self._body_lines: list[str] = []
        self._footer: str = ""

    def body(self, key: str, **kwargs: str) -> MessageTemplate:
        """Append a translated body line."""
        self._body_lines.append(self._i18n.get(key, **kwargs))
        return self

    def raw(self, text: str) -> MessageTemplate:
        """Append a raw (already-formatted) body line."""
        self._body_lines.append(text)
        return self

    def footer(self, key: str, **kwargs: str) -> MessageTemplate:
        """Set the footer hint line."""
        self._footer = self._i18n.get(key, **kwargs)
        return self

    def build(self) -> str:
        """Assemble and return the formatted message, truncating if needed."""
        parts = [f"<b>{self._title}</b>", _DIVIDER]
        parts.extend(self._body_lines)
        if self._footer:
            parts.extend(["", self._footer])
        text = "\n".join(parts)
        return truncate(text)


def truncate(text: str, limit: int = TELEGRAM_SAFE_LIMIT) -> str:
    """Truncate text to *limit* characters, appending '…' if needed."""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def format_status_badge(status: str, icons: dict[str, str]) -> str:
    """Return an icon + status string from a status icon map."""
    icon = icons.get(status, "❓")
    return f"{icon} {status}"


def error_template(key: str, i18n: I18nContext) -> str:
    """Return a short error message with a standard ❌ prefix."""
    return f"❌ {i18n.get(key)}"


def progress_template(title: str, percent: int) -> str:
    """Return a visual progress bar message.

    Args:
        title: Human-readable description of the ongoing work.
        percent: 0–100.
    """
    filled = int(percent / 10)
    bar = "█" * filled + "░" * (10 - filled)
    return f"⏳ <b>{title}</b>\n[{bar}] {percent}%"
