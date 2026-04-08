"""Unit tests for negotiations session availability classification."""

from src.services.hh_ui.applicant_negotiations_http import classify_negotiations_session_fetch


def test_classify_http_error_returns_error() -> None:
    status, detail = classify_negotiations_session_fetch(None, "http_403", None)
    assert status == "error"
    assert detail == "http_403"


def test_classify_empty_html_without_err_returns_error() -> None:
    status, detail = classify_negotiations_session_fetch(None, None, "https://hh.ru/foo")
    assert status == "error"
    assert detail == "empty_response"


def test_classify_login_redirect() -> None:
    status, detail = classify_negotiations_session_fetch(
        "<html>login</html>",
        None,
        "https://hh.ru/account/login?backurl=...",
    )
    assert status == "login"
    assert detail is None


def test_classify_unexpected_path_not_negotiations() -> None:
    status, detail = classify_negotiations_session_fetch(
        "<html>ok</html>",
        None,
        "https://hh.ru/applicant/resumes",
    )
    assert status == "unexpected_url"
    assert detail is None


def test_classify_ok_on_negotiations_path() -> None:
    status, detail = classify_negotiations_session_fetch(
        "<html>list</html>",
        None,
        "https://hh.ru/applicant/negotiations",
    )
    assert status == "ok"
    assert detail is None


def test_classify_ok_regional_host() -> None:
    status, detail = classify_negotiations_session_fetch(
        "<html></html>",
        None,
        "https://izhevsk.hh.ru/applicant/negotiations?page=1",
    )
    assert status == "ok"
    assert detail is None
