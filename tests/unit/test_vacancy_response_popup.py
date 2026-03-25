"""Tests for HH vacancy_response/popup helpers."""

from src.services.hh_ui.outcomes import ApplyOutcome
from src.services.hh_ui.vacancy_response_popup import _cap_raw_body_for_log, map_popup_json_to_apply_result


def test_cap_raw_body_for_log_truncates_at_64k():
    long = "x" * (64 * 1024 + 100)
    capped, n, truncated = _cap_raw_body_for_log(long)
    assert n == 64 * 1024 + 100
    assert truncated is True
    assert len(capped) == 64 * 1024


def test_cap_raw_body_for_log_no_truncation():
    s = '{"a": 1}'
    capped, n, truncated = _cap_raw_body_for_log(s)
    assert capped == s
    assert n == len(s)
    assert truncated is False


def test_map_popup_json_unknown_error():
    data = {"success": False, "errors": [{"value": "unknown"}]}
    r = map_popup_json_to_apply_result(data)
    assert r is not None
    assert r.outcome == ApplyOutcome.ERROR
    assert "unknown" in (r.detail or "")
