"""HH UI apply retry classification and backoff (no Playwright)."""

import pytest

from src.services.hh_ui.apply_retry import (
    apply_outcome_is_retryable,
    apply_outcome_is_terminal_no_retry,
    apply_retry_delay_seconds,
)
from src.services.hh_ui.outcomes import ApplyOutcome


@pytest.mark.parametrize(
    "outcome,terminal",
    [
        (ApplyOutcome.SUCCESS, True),
        (ApplyOutcome.ALREADY_RESPONDED, True),
        (ApplyOutcome.EMPLOYER_QUESTIONS, True),
        (ApplyOutcome.VACANCY_UNAVAILABLE, True),
        (ApplyOutcome.ERROR, False),
        (ApplyOutcome.CAPTCHA, False),
    ],
)
def test_terminal_no_retry(outcome: ApplyOutcome, terminal: bool) -> None:
    assert apply_outcome_is_terminal_no_retry(outcome) is terminal


@pytest.mark.parametrize(
    "outcome,retryable",
    [
        (ApplyOutcome.ERROR, True),
        (ApplyOutcome.RATE_LIMITED, True),
        (ApplyOutcome.NO_APPLY_BUTTON, True),
        (ApplyOutcome.SESSION_EXPIRED, True),
        (ApplyOutcome.CAPTCHA, False),
        (ApplyOutcome.SUCCESS, False),
    ],
)
def test_retryable(outcome: ApplyOutcome, retryable: bool) -> None:
    assert apply_outcome_is_retryable(outcome) is retryable


def test_retry_delay_exponential_cap() -> None:
    assert apply_retry_delay_seconds(0, 10.0, 600.0) == 10.0
    assert apply_retry_delay_seconds(1, 10.0, 600.0) == 20.0
    assert apply_retry_delay_seconds(2, 10.0, 600.0) == 40.0
    assert apply_retry_delay_seconds(10, 10.0, 25.0) == 25.0
