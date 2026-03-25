"""Tests for HH vacancy_response/popup helpers."""

from src.services.hh_ui.outcomes import ApplyOutcome
from src.services.hh_ui.vacancy_response_popup import (
    _popup_post_url,
    build_popup_apply_curl_command,
    map_popup_json_to_apply_result,
    _cap_raw_body_for_log,
)


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


def test_map_popup_errors_value_unknown_still_error():
    """errors[].value \"unknown\" is not the same as top-level error \"unknown\"."""
    data = {"success": False, "errors": [{"value": "unknown"}]}
    r = map_popup_json_to_apply_result(data)
    assert r is not None
    assert r.outcome == ApplyOutcome.ERROR
    assert "unknown" in (r.detail or "")


def test_map_popup_top_level_error_unknown():
    r = map_popup_json_to_apply_result({"error": "unknown"})
    assert r is not None
    assert r.outcome == ApplyOutcome.VACANCY_UNAVAILABLE
    assert r.detail == "popup_api:unknown"


def test_map_popup_errors_type_not_found():
    r = map_popup_json_to_apply_result(
        {
            "description": "Not Found",
            "errors": [{"type": "not_found"}],
            "request_id": "x",
        }
    )
    assert r is not None
    assert r.outcome == ApplyOutcome.VACANCY_UNAVAILABLE
    assert r.detail == "popup_api:not_found"


def test_popup_post_url():
    assert _popup_post_url("https://izhevsk.hh.ru/vacancy/1") == (
        "https://izhevsk.hh.ru/applicant/vacancy_response/popup"
    )


def test_build_popup_apply_curl_command_shape():
    url = "https://hh.ru/vacancy/123"
    post = "https://hh.ru/applicant/vacancy_response/popup"
    curl = build_popup_apply_curl_command(
        vacancy_url=url,
        post_url=post,
        cookie_header="a=b; c=d",
        xsrf="tok",
        vacancy_id="123",
        resume_hash="resumehash",
        letter="hi",
        hhtm_from="vacancy_search_list",
    )
    assert "curl" in curl
    assert post in curl
    assert "Cookie: a=b; c=d" in curl
    assert "X-Xsrftoken: tok" in curl or "X-Xsrftoken" in curl
    assert "-F" in curl
    assert "vacancy_id=123" in curl.replace("'", "")
