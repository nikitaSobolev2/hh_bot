"""Login assist runner: do not persist session while still on login page."""

from unittest.mock import MagicMock

from src.services.hh_ui.login_assist_runner import _login_assist_ready


def _minimal_logged_in_cookies() -> dict:
    """Cookies that trigger is_logged_in_storage_state via hhtoken (len > 10)."""
    return {
        "cookies": [
            {
                "name": "hhtoken",
                "value": "x" * 64,
                "domain": ".hh.ru",
                "path": "/",
            }
        ],
        "origins": [],
    }


def _page(url: str, login_form_count: int = 0) -> MagicMock:
    p = MagicMock()
    p.url = url
    p.locator.return_value.count.return_value = login_form_count
    return p


def test_login_assist_not_ready_on_account_login_url() -> None:
    ctx = MagicMock()
    ctx.pages = [_page("https://hh.ru/account/login")]
    raw = _minimal_logged_in_cookies()
    assert _login_assist_ready(ctx, raw) is False


def test_login_assist_ready_after_login_url_gone() -> None:
    ctx = MagicMock()
    ctx.pages = [_page("https://hh.ru/")]
    raw = _minimal_logged_in_cookies()
    assert _login_assist_ready(ctx, raw) is True


def test_login_assist_not_ready_when_login_form_visible() -> None:
    ctx = MagicMock()
    ctx.pages = [_page("https://hh.ru/account/applicant", login_form_count=1)]
    raw = _minimal_logged_in_cookies()
    assert _login_assist_ready(ctx, raw) is False


def test_login_assist_ready_when_second_tab_left_login() -> None:
    """First tab still on /account/login; user logged in on another tab (common on hh.ru)."""
    ctx = MagicMock()
    ctx.pages = [
        _page("https://hh.ru/account/login"),
        _page("https://hh.ru/"),
    ]
    raw = _minimal_logged_in_cookies()
    assert _login_assist_ready(ctx, raw) is True
