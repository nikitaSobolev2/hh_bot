"""Shared text formatters for common domain objects.

All format functions are pure (no I/O, no side effects) and return HTML strings
ready to be embedded in Telegram messages.
"""

from __future__ import annotations

from src.core.constants import TASK_STATUS_ICONS


def format_work_experience_line(
    company_name: str,
    title: str | None = None,
    period: str | None = None,
    stack: str | None = None,
) -> str:
    """Return a single-line summary for a work experience entry."""
    parts = [f"<b>{company_name}</b>"]
    if title:
        parts.append(f"— {title}")
    if period:
        parts.append(f"({period})")
    if stack:
        parts.append(f"<code>[{stack}]</code>")
    return " ".join(parts)


def format_task_status(status: str) -> str:
    """Return icon + status text for a Celery task status."""
    icon = TASK_STATUS_ICONS.get(status, "❓")
    return f"{icon} {status}"


def format_vacancy_preview(
    title: str,
    company_name: str | None = None,
    salary: str | None = None,
    url: str | None = None,
) -> str:
    """Return a compact vacancy preview for inline lists."""
    parts = [f"<b>{title}</b>"]
    if company_name:
        parts.append(company_name)
    if salary:
        parts.append(f"💰 {salary}")
    text = "\n".join(parts)
    if url:
        text += f'\n<a href="{url}">🔗 Открыть вакансию</a>'
    return text


def format_page_counter(page: int, total_pages: int) -> str:
    """Return a human-readable page indicator: «Стр. 2 / 5»."""
    return f"Стр. {page + 1} / {total_pages}" if total_pages > 0 else ""


def format_keyword_list(keywords: list[tuple[str, int]], top_n: int = 15) -> str:
    """Return a compact HTML keyword list with counts."""
    total = sum(c for _, c in keywords)
    lines = []
    for rank, (kw, count) in enumerate(keywords[:top_n], 1):
        pct = f"{count / total * 100:.1f}%" if total else "—"
        lines.append(f"  {rank}. <code>{kw}</code> — {count} ({pct})")
    return "\n".join(lines)
