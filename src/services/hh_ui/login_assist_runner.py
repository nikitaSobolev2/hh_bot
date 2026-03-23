"""Sync Playwright: open hh.ru login and wait until storage_state reflects a logged-in session."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from playwright.sync_api import sync_playwright

from src.config import settings
from src.services.hh_ui.browser_link import is_logged_in_storage_state, validate_playwright_storage_state
from src.services.hh_ui.runner import _detect_captcha, _detect_login


class LoginAssistOutcome(str, Enum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    CAPTCHA = "captcha"
    ERROR = "error"


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
            browser = p.chromium.launch(headless=config.headless)
            try:
                context = browser.new_context()
                page = context.new_page()
                page.goto(
                    config.login_url,
                    wait_until="domcontentloaded",
                    timeout=config.navigation_timeout_ms,
                )

                while time.monotonic() < deadline:
                    if _detect_captcha(page):
                        return None, LoginAssistOutcome.CAPTCHA, None

                    try:
                        raw = context.storage_state()
                    except Exception as exc:
                        last_error = str(exc)[:500]
                        time.sleep(config.poll_interval_seconds)
                        continue

                    if is_logged_in_storage_state(raw):
                        try:
                            validate_playwright_storage_state(raw)
                        except ValueError as exc:
                            last_error = str(exc)
                            time.sleep(config.poll_interval_seconds)
                            continue
                        return raw, LoginAssistOutcome.SUCCESS, None

                    if not _detect_login(page):
                        try:
                            raw = context.storage_state()
                            if is_logged_in_storage_state(raw):
                                validate_playwright_storage_state(raw)
                                return raw, LoginAssistOutcome.SUCCESS, None
                        except ValueError:
                            pass

                    time.sleep(config.poll_interval_seconds)

                return None, LoginAssistOutcome.TIMEOUT, last_error
            finally:
                browser.close()
    except Exception as exc:
        return None, LoginAssistOutcome.ERROR, str(exc)[:500]
