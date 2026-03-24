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


def test_login_assist_not_ready_on_account_login_url() -> None:
    page = MagicMock()
    page.url = "https://hh.ru/account/login"
    page.locator.return_value.count.return_value = 0
    raw = _minimal_logged_in_cookies()
    assert _login_assist_ready(page, raw) is False


def test_login_assist_ready_after_login_url_gone() -> None:
    page = MagicMock()
    page.url = "https://hh.ru/"
    page.locator.return_value.count.return_value = 0
    raw = _minimal_logged_in_cookies()
    assert _login_assist_ready(page, raw) is True


def test_login_assist_not_ready_when_login_form_visible() -> None:
    page = MagicMock()
    page.url = "https://hh.ru/account/applicant"
    loc = MagicMock()
    loc.count.return_value = 1
    page.locator.return_value = loc
    raw = _minimal_logged_in_cookies()
    assert _login_assist_ready(page, raw) is False
