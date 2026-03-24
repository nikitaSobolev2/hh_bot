"""Sync Playwright: open hh.ru login and wait until storage_state reflects a logged-in session."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from playwright.sync_api import BrowserContext, sync_playwright

from src.config import settings
from src.services.hh_ui.browser_link import is_logged_in_storage_state, validate_playwright_storage_state
from src.services.hh_ui.playwright_support import CHROMIUM_LAUNCH_ARGS, dispose_sync_browser_context
from src.services.hh_ui.runner import _detect_captcha

# Do not use LOGIN_FORM's `a[href*="account/login"]`: CDN/aux tabs often include that link in
# the footer, so every tab would look "on login" and login assist would never finish.
_LOGIN_ASSIST_SCREEN_HINTS: tuple[str, ...] = (
    '[data-qa="login"]',
    "text=Вход в личный кабинет",
)


def _detect_login_assist(page: Any) -> bool:
    """True if this tab is the real login screen (not a random page with a login link in chrome)."""
    for hint in _LOGIN_ASSIST_SCREEN_HINTS:
        try:
            if page.locator(hint).count() > 0:
                return True
        except Exception:
            continue
    u = (page.url or "").lower()
    return "/account/login" in u or "/account/signup" in u


class LoginAssistOutcome(str, Enum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    CAPTCHA = "captcha"
    ERROR = "error"


def _any_page_off_login_screen(context: BrowserContext) -> bool:
    """True if at least one tab is not the login form (handles hh.ru opening login in a new tab)."""
    for pg in context.pages:
        try:
            if not _detect_login_assist(pg):
                return True
        except Exception:
            continue
    return False


def _any_page_has_captcha(context: BrowserContext) -> bool:
    for pg in context.pages:
        try:
            if _detect_captcha(pg):
                return True
        except Exception:
            continue
    return False


def _login_assist_ready(context: BrowserContext, raw: dict[str, Any]) -> bool:
    """True when cookies look logged-in and at least one tab has left the login screen.

    hh.ru may set hhtoken before credentials are submitted — require no real login UI on *some* tab.
    If the user completes login in a second tab, the first tab may still show /account/login;
    polling only the initial page would never finish. Footer links to account/login on CDN/aux
    tabs must not count as "still on login" (see _detect_login_assist).
    """
    if not is_logged_in_storage_state(raw):
        return False
    try:
        validate_playwright_storage_state(raw)
    except ValueError:
        return False
    return _any_page_off_login_screen(context)


@dataclass(frozen=True, slots=True)
class HhLoginAssistRunnerConfig:
    login_url: str
    max_wait_seconds: int
    poll_interval_seconds: float
    headless: bool
    navigation_timeout_ms: int

    @classmethod
    def from_settings(cls) -> HhLoginAssistRunnerConfig:
        return cls(
            login_url=(settings.hh_login_assist_login_url or "https://hh.ru/account/login").strip(),
            max_wait_seconds=int(settings.hh_login_assist_max_wait_seconds),
            poll_interval_seconds=float(settings.hh_login_assist_poll_interval_seconds),
            headless=bool(settings.hh_login_assist_headless),
            navigation_timeout_ms=int(settings.hh_ui_navigation_timeout_ms),
        )


def run_login_assist_sync(
    config: HhLoginAssistRunnerConfig,
) -> tuple[dict[str, Any] | None, LoginAssistOutcome, str | None]:
    """Launch Chromium, open login URL, poll until logged-in storage_state or timeout.

    Returns (storage_state or None, outcome, error_detail).
    """
    deadline = time.monotonic() + float(config.max_wait_seconds)
    last_error: str | None = None

    try:
        with sync_playwright() as p:
            browser = None
            context = None
            try:
                browser = p.chromium.launch(
                    headless=config.headless,
                    args=list(CHROMIUM_LAUNCH_ARGS),
                )
                context = browser.new_context()
                page = context.new_page()
                page.goto(
                    config.login_url,
                    wait_until="domcontentloaded",
                    timeout=config.navigation_timeout_ms,
                )

                while time.monotonic() < deadline:
                    if _any_page_has_captcha(context):
                        return None, LoginAssistOutcome.CAPTCHA, None

                    try:
                        raw = context.storage_state()
                    except Exception as exc:
                        last_error = str(exc)[:500]
                        time.sleep(config.poll_interval_seconds)
                        continue

                    if _login_assist_ready(context, raw):
                        return raw, LoginAssistOutcome.SUCCESS, None

                    time.sleep(config.poll_interval_seconds)

                return None, LoginAssistOutcome.TIMEOUT, last_error
            finally:
                dispose_sync_browser_context(context, browser)
    except Exception as exc:
        return None, LoginAssistOutcome.ERROR, str(exc)[:500]
