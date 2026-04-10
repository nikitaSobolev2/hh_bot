"""Helpers for deciding whether stored AI compatibility is usable."""

from __future__ import annotations


def compatibility_score_needs_regeneration(score: float | None) -> bool:
    """True when the score should be treated as missing and regenerated."""
    if score is None:
        return True
    try:
        return float(score) <= 0.0
    except (TypeError, ValueError):
        return True


def compatibility_score_is_usable(score: float | None) -> bool:
    """True when the score can be trusted for filtering/reuse."""
    return not compatibility_score_needs_regeneration(score)
