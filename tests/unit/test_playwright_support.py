"""Tests for shared Playwright browser slot and crash detection."""

import time

from playwright.sync_api import Error as PlaywrightError

from src.services.hh_ui.playwright_support import (
    is_playwright_browser_dead_error,
    playwright_browser_slot_sync,
)


def test_is_playwright_browser_dead_error_detects_page_crashed() -> None:
    exc = PlaywrightError("Page.goto: Page crashed\nCall log:\n  - navigating")
    assert is_playwright_browser_dead_error(exc) is True


def test_is_playwright_browser_dead_error_detects_target_crashed() -> None:
    exc = PlaywrightError("Page.evaluate: Target crashed")
    assert is_playwright_browser_dead_error(exc) is True


def test_is_playwright_browser_dead_error_ignores_timeout() -> None:
    exc = PlaywrightError("Timeout 60000ms exceeded")
    assert is_playwright_browser_dead_error(exc) is False


def test_playwright_browser_slot_sync_acquires_and_releases(monkeypatch) -> None:
    state = {"token": None}

    class FakeRedis:
        def set(self, key, token, nx=False, ex=None):
            if state["token"] is None:
                state["token"] = token
                return True
            return False

        def eval(self, script, numkeys, key, token):
            if state["token"] == token:
                state["token"] = None
                return 1
            return 0

        def close(self):
            return None

    monkeypatch.setattr(
        "src.services.hh_ui.playwright_support.create_sync_redis",
        lambda: FakeRedis(),
    )

    with playwright_browser_slot_sync():
        assert state["token"] is not None
    assert state["token"] is None


def test_playwright_browser_slot_sync_renews_lock_while_held(monkeypatch) -> None:
    state = {"token": None, "expires": None}

    class FakeRedis:
        def set(self, key, token, nx=False, ex=None):
            if state["token"] is None:
                state["token"] = token
                state["expires"] = ex
                return True
            return False

        def eval(self, script, numkeys, key, *args):
            if "expire" in script and state["token"] == args[0]:
                state["expires"] = int(args[1])
                return 1
            if state["token"] == args[0]:
                state["token"] = None
                return 1
            return 0

        def close(self):
            return None

    monkeypatch.setattr(
        "src.services.hh_ui.playwright_support.create_sync_redis",
        lambda: FakeRedis(),
    )
    monkeypatch.setattr(
        "src.services.hh_ui.playwright_support.settings",
        type(
            "S",
            (),
            {
                "playwright_browser_lock_ttl_seconds": 120,
                "playwright_browser_lock_renew_interval_seconds": 0.05,
                "playwright_browser_lock_wait_seconds": 1.0,
            },
        )(),
    )

    with playwright_browser_slot_sync():
        time.sleep(0.12)
        assert state["expires"] == 120

