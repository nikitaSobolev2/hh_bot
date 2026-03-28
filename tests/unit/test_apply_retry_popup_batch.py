"""HH UI popup batch retry policy (negotiations limit)."""

from src.services.hh_ui.apply_retry import apply_result_should_retry_popup_batch
from src.services.hh_ui.outcomes import ApplyOutcome, ApplyResult


def test_negotiations_limit_not_retried() -> None:
    r = ApplyResult(
        outcome=ApplyOutcome.ERROR,
        detail="popup_api:negotiations-limit-exceeded",
    )
    assert apply_result_should_retry_popup_batch(r) is False


def test_generic_error_still_retried() -> None:
    r = ApplyResult(outcome=ApplyOutcome.ERROR, detail="popup_api:other")
    assert apply_result_should_retry_popup_batch(r) is True
