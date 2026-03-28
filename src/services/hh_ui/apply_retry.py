"""Retry policy for HH UI apply outcomes (Playwright)."""

from __future__ import annotations

from src.services.hh_ui.outcomes import ApplyOutcome, ApplyResult


def apply_outcome_is_terminal_no_retry(outcome: ApplyOutcome) -> bool:
    """Success, already applied, employer questions, or vacancy gone — do not retry."""
    return outcome in (
        ApplyOutcome.SUCCESS,
        ApplyOutcome.ALREADY_RESPONDED,
        ApplyOutcome.EMPLOYER_QUESTIONS,
        ApplyOutcome.VACANCY_UNAVAILABLE,
    )


def apply_outcome_is_retryable(outcome: ApplyOutcome) -> bool:
    """Transient UI/network/session issues — retry with backoff before giving up."""
    return outcome in (
        ApplyOutcome.ERROR,
        ApplyOutcome.RATE_LIMITED,
        ApplyOutcome.NO_APPLY_BUTTON,
        ApplyOutcome.SESSION_EXPIRED,
    )


def apply_result_should_retry_popup_batch(result: ApplyResult) -> bool:
    """Popup batch: do not retry HH ``negotiations-limit-exceeded`` (account-wide cap)."""
    if "negotiations-limit-exceeded" in (result.detail or "").lower():
        return False
    return apply_outcome_is_retryable(result.outcome)


def apply_retry_delay_seconds(attempt: int, initial_seconds: float, cap_seconds: float) -> float:
    """Exponential backoff: initial * 2**attempt, capped."""
    if attempt < 0:
        attempt = 0
    delay = initial_seconds * (2**attempt)
    return float(min(delay, cap_seconds))
