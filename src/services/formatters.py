"""Shared domain formatters used across Celery tasks and bot handlers.

All functions are pure — no I/O, no side effects.
"""

from __future__ import annotations


def format_work_experience_summary(
    company_name: str,
    title: str | None = None,
    period: str | None = None,
    stack: str | None = None,
) -> str:
    """Format a compact work experience summary line.

    Used in task prompts and progress messages.  Returns a plain-text line
    (no HTML) suitable for embedding in AI prompts or plain message bodies.
    """
    parts = [company_name]
    if title:
        parts.append(f"— {title}")
    if period:
        parts.append(f"({period})")
    if stack:
        parts.append(f"[{stack}]")
    return " ".join(parts)


def format_work_experience_block(experiences: list) -> str:
    """Format a list of work experience objects into a multi-line summary.

    Each experience must have ``company_name``, ``title``, ``period``, and ``stack``
    attributes (all optional except ``company_name``).
    """
    return "; ".join(
        format_work_experience_summary(
            company_name=exp.company_name,
            title=getattr(exp, "title", None),
            period=getattr(exp, "period", None),
            stack=getattr(exp, "stack", None),
        )
        for exp in experiences
    )
