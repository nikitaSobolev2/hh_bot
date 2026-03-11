"""Parser for structured AI interview analysis responses."""

from __future__ import annotations

import re

_SUMMARY_PATTERN = re.compile(
    r"\[InterviewSummaryStart\](.*?)\[InterviewSummaryEnd\]",
    re.DOTALL,
)
_IMPROVE_PATTERN = re.compile(
    r"\[ImproveStart\]:(.+?)\n(.*?)\[ImproveEnd\]:\1",
    re.DOTALL,
)


def parse_interview_analysis(text: str) -> tuple[str, list[dict[str, str]]]:
    """Parse the structured AI response into a summary and improvement blocks.

    Returns a tuple of:
    - summary: overall interview assessment text
    - improvements: list of dicts with 'title' and 'summary' keys

    Handles missing or malformed blocks gracefully by returning empty values.
    """
    summary_match = _SUMMARY_PATTERN.search(text)
    summary = summary_match.group(1).strip() if summary_match else text.strip()

    improvements: list[dict[str, str]] = []
    for match in _IMPROVE_PATTERN.finditer(text):
        title = match.group(1).strip()
        block_summary = match.group(2).strip()
        if title and block_summary:
            improvements.append({"title": title, "summary": block_summary})

    return summary, improvements
