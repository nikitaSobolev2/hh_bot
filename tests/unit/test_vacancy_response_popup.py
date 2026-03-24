"""Unit tests for vacancy_response_popup (no Playwright)."""

from src.services.hh_ui.outcomes import ApplyOutcome
from src.services.hh_ui.vacancy_response_popup import (
    extract_xsrf_token,
    hhtm_from_for_popup,
    map_popup_json_to_apply_result,
    parse_vacancy_id_from_url,
)


def test_parse_vacancy_id_from_url() -> None:
    assert parse_vacancy_id_from_url("https://izhevsk.hh.ru/vacancy/131481403?x=1") == "131481403"
    assert parse_vacancy_id_from_url("https://hh.ru/vacancy/42") == "42"
    assert parse_vacancy_id_from_url("https://example.com/foo") is None


def test_hhtm_from_for_popup() -> None:
    assert hhtm_from_for_popup("https://hh.ru/vacancy/1?hhtmFrom=vacancy_search_list") == "vacancy_search_list"
    assert hhtm_from_for_popup("https://hh.ru/vacancy/1") == "vacancy_search_list"


def test_extract_xsrf_token_hidden_input() -> None:
    html = '<form><input type="hidden" name="_xsrf" value="abc123token" /></form>'
    assert extract_xsrf_token(html) == "abc123token"


def test_extract_xsrf_token_meta() -> None:
    html = '<head><meta name="_xsrf" content="meta-xsrf-99" /></head>'
    assert extract_xsrf_token(html) == "meta-xsrf-99"


def test_map_popup_json_success_string() -> None:
    r = map_popup_json_to_apply_result({"success": "true", "vacancy_id": "1"})
    assert r is not None
    assert r.outcome == ApplyOutcome.SUCCESS
    assert r.detail == "popup_api"


def test_map_popup_json_required_additional() -> None:
    r = map_popup_json_to_apply_result({"success": "false", "requiredAdditionalData": ["PHOTO"]})
    assert r is not None
    assert r.outcome == ApplyOutcome.EMPLOYER_QUESTIONS
    assert "PHOTO" in (r.detail or "")


def test_map_popup_json_errors_list() -> None:
    r = map_popup_json_to_apply_result(
        {"success": "false", "errors": [{"value": "уже откликались"}]}
    )
    assert r is not None
    assert r.outcome == ApplyOutcome.ALREADY_RESPONDED


def test_map_popup_json_unmapped_returns_none() -> None:
    assert map_popup_json_to_apply_result({"foo": "bar"}) is None
