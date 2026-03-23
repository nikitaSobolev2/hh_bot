"""Tests for Playwright storage_state validation and hh user id guessing."""

import pytest

from src.services.hh_ui.browser_link import (
    guess_hh_user_id_from_storage,
    make_hh_user_id_for_browser_link,
    validate_playwright_storage_state,
)


def test_validate_rejects_non_object() -> None:
    with pytest.raises(ValueError, match="not-a-json-object"):
        validate_playwright_storage_state([])


def test_validate_requires_cookies_array() -> None:
    with pytest.raises(ValueError, match="missing-cookies-array"):
        validate_playwright_storage_state({"origins": []})


def test_validate_requires_hh_domain_cookie() -> None:
    with pytest.raises(ValueError, match="no-hh-cookies"):
        validate_playwright_storage_state({"cookies": [{"domain": "example.com", "name": "a", "value": "b"}]})


def test_validate_accepts_hh_cookie() -> None:
    state = {
        "cookies": [{"domain": ".hh.ru", "name": "uid", "value": "12345"}],
        "origins": [],
    }
    assert validate_playwright_storage_state(state) == state


def test_guess_uid_from_cookie() -> None:
    state = {
        "cookies": [{"domain": ".hh.ru", "name": "uid", "value": "999"}],
    }
    assert guess_hh_user_id_from_storage(state) == "999"


def test_make_id_falls_back_to_random_prefix() -> None:
    state = {"cookies": [{"domain": ".hh.ru", "name": "x", "value": "y"}]}
    uid = make_hh_user_id_for_browser_link(state)
    assert uid.startswith("browser_")
    assert len(uid) > len("browser_")
