"""Tests for applicant resume list HTTP parse (no Playwright)."""

from pathlib import Path

import httpx

from src.services.hh_ui.applicant_http import (
    html_suggests_captcha,
    html_suggests_login,
    httpx_cookies_from_storage_state,
    parse_applicant_resumes_from_html,
    url_is_applicant_resumes_document,
    url_suggests_login_page,
)

_ROOT = Path(__file__).resolve().parents[2]


def test_sample_applicant_html_not_detected_as_login() -> None:
    html = (_ROOT / "docs" / "applicant-resumes-block.html").read_text(encoding="utf-8")
    assert html_suggests_login(html) is False


def test_parse_applicant_resumes_from_sample_html() -> None:
    html = (_ROOT / "docs" / "applicant-resumes-block.html").read_text(encoding="utf-8")
    result = parse_applicant_resumes_from_html(html)
    assert result.outcome.value == "success"
    assert len(result.resumes) == 3
    by_id = {r.id: r.title for r in result.resumes}
    assert by_id["8e224251ff10218b5f0039ed1f7450507a696d"] == "Frontend-разработчик"
    assert by_id["22e1313dff10218a5b0039ed1f494848613448"] == "Backend-разработчик"
    assert by_id["df3c734dff0f2fd73c0039ed1f396734705750"] == "Fullstack-разработчик"


def test_parse_applicant_resumes_empty() -> None:
    result = parse_applicant_resumes_from_html("<html><body></body></html>")
    assert result.outcome.value == "error"
    assert result.detail == "no_resume_links"


def test_html_suggests_captcha_false_on_noise() -> None:
    """iframe + word 'captcha' in JS must not imply a challenge (common false positive)."""
    html = """
    <html><body><iframe src="https://mc.yandex.ru/foo"></iframe>
    <script>var x = "precaptcha_mode";</script></body></html>
    """
    assert html_suggests_captcha(html) is False


def test_html_suggests_captcha_true_when_smartcaptcha_iframe() -> None:
    html = (
        '<iframe src="https://smartcaptcha.yandex.ru/captcha?foo=1" width="100"></iframe>'
    )
    assert html_suggests_captcha(html) is True


def test_html_suggests_captcha_false_on_sample_applicant_html() -> None:
    html = (_ROOT / "docs" / "applicant-resumes-block.html").read_text(encoding="utf-8")
    assert html_suggests_captcha(html) is False


def test_html_suggests_login_false_when_resume_list_present() -> None:
    """Footer links to account/login on authenticated pages must not look like expired session."""
    html = """
    <html><body>
    <a href="/account/login">Вход</a>
    <a data-qa="resume-card-link-abc123" href="/resume/abc">x</a>
    </body></html>
    """
    assert html_suggests_login(html) is False


def test_url_suggests_login_page() -> None:
    assert url_suggests_login_page("https://hh.ru/account/login?back=...") is True
    assert url_suggests_login_page("https://hh.ru/applicant/resumes") is False


def test_url_is_applicant_resumes_document() -> None:
    assert url_is_applicant_resumes_document("https://hh.ru/applicant/resumes") is True
    assert url_is_applicant_resumes_document("https://spb.hh.ru/applicant/resumes") is True
    assert url_is_applicant_resumes_document("https://hh.ru/account/login") is False


def test_httpx_cookies_from_storage_state_filters_hh() -> None:
    state = {
        "cookies": [
            {"name": "a", "value": "1", "domain": ".hh.ru", "path": "/", "expires": -1},
            {"name": "b", "value": "2", "domain": "other.com", "path": "/", "expires": -1},
        ]
    }
    jar = httpx_cookies_from_storage_state(state)
    assert isinstance(jar, httpx.Cookies)
    assert jar.get("a", domain=".hh.ru") == "1"
