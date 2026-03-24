"""Tests for applicant resume list HTTP parse (no Playwright)."""

from pathlib import Path

import httpx

from src.services.hh_ui.applicant_http import (
    httpx_cookies_from_storage_state,
    parse_applicant_resumes_from_html,
)

_ROOT = Path(__file__).resolve().parents[2]


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
