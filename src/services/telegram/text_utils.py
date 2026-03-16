"""Text utilities for Telegram message formatting and splitting."""

from __future__ import annotations

import re

from src.core.constants import TELEGRAM_SAFE_LIMIT

BREAK_MARKER = "[BREAK]"

_SUMMARY_PATTERN = re.compile(
    r"<Summary>\s*(.*?)\s*</Summary>",
    re.DOTALL | re.IGNORECASE,
)
_PLAN_PATTERN = re.compile(
    r"<Plan>\s*(.*?)\s*</Plan>",
    re.DOTALL | re.IGNORECASE,
)


def parse_deep_learning_response(text: str) -> tuple[str | None, str | None]:
    """Extract <Summary> and <Plan> blocks from deep learning AI response.

    Returns (summary, plan). If parsing fails (missing or malformed tags),
    returns (None, None) so callers can fall back to full text.
    """
    if not text or not text.strip():
        return (None, None)
    summary_match = _SUMMARY_PATTERN.search(text)
    plan_match = _PLAN_PATTERN.search(text)
    summary = summary_match.group(1).strip() if summary_match else None
    plan = plan_match.group(1).strip() if plan_match else None
    return (summary, plan)


def split_text_by_break(
    text: str,
    break_marker: str = BREAK_MARKER,
    max_len: int = TELEGRAM_SAFE_LIMIT,
) -> list[str]:
    """Split text by [BREAK] marker. If a chunk exceeds max_len, sub-split with length."""
    if not text or not text.strip():
        return []
    parts = [p.strip() for p in text.split(break_marker) if p.strip()]
    if not parts:
        return []
    if len(parts) == 1 and len(parts[0]) <= max_len:
        return parts
    result: list[str] = []
    for part in parts:
        if len(part) <= max_len:
            result.append(part)
        else:
            result.extend(split_text_for_telegram(part, max_len=max_len))
    return result


def split_text_for_telegram(
    text: str,
    max_len: int = TELEGRAM_SAFE_LIMIT,
) -> list[str]:
    """Split text into chunks at paragraph or line boundaries, never exceeding max_len.

    Prefers splitting at double newlines (paragraphs), then single newlines (lines),
    then hard-splits at max_len if a line exceeds the limit.
    """
    if not text or not text.strip():
        return []
    if len(text) <= max_len:
        return [text.strip()]

    chunks: list[str] = []
    remaining = text.strip()

    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break

        chunk_end = max_len
        search_region = remaining[: max_len + 1]

        # Prefer split at paragraph boundary (\n\n)
        last_para = search_region.rfind("\n\n")
        if last_para > 0:
            chunk_end = last_para + 2  # Include both newlines
        else:
            # Fall back to line boundary (\n)
            last_newline = search_region.rfind("\n")
            if last_newline > 0:
                chunk_end = last_newline + 1
            # else: hard split at max_len

        chunk = remaining[:chunk_end].rstrip()
        remaining = remaining[chunk_end:].lstrip()
        if chunk:
            chunks.append(chunk)

    return chunks
