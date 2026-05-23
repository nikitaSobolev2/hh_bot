"""Shared Chromium launch options and teardown for sync Playwright runs."""

from __future__ import annotations

import contextlib
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from src.core.logging import get_logger
from src.core.redis import create_sync_redis

logger = get_logger(__name__)

# Docker: small /dev/shm causes Chromium crashes; headless Linux: drop GPU overhead.
CHROMIUM_LAUNCH_ARGS: tuple[str, ...] = (
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--no-first-run",
    "--no-default-browser-check",
)

# Fixed desktop viewport so Magritte bottom-sheet selectors match desktop layouts.
HH_UI_VIEWPORT: dict[str, int] = {"width": 1280, "height": 900}

_PLAYWRIGHT_BROWSER_LOCK_KEY = "lock:playwright:chromium"
_PLAYWRIGHT_BROWSER_LOCK_TTL_S = 900
_PLAYWRIGHT_BROWSER_LOCK_WAIT_S = 240.0
_PLAYWRIGHT_BROWSER_LOCK_POLL_S = 0.25
_CHROMIUM_LAUNCH_TIMEOUT_MS = 120_000

_RELEASE_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class PlaywrightBrowserSlotTimeoutError(TimeoutError):
    """Raised when no global Playwright browser slot becomes free in time."""


def is_playwright_browser_dead_error(exc: BaseException) -> bool:
    """True when Playwright page/context/browser died (crash, OOM, or explicit close)."""
    name = type(exc).__name__
    if "TargetClosed" in name or "BrowserClosed" in name:
        return True
    msg = str(exc).lower()
    markers = (
        "has been closed",
        "target closed",
        "target crashed",
        "browser has been closed",
        "page crashed",
        "browser crashed",
    )
    return any(marker in msg for marker in markers)


def _acquire_playwright_browser_slot_sync() -> str:
    token = uuid.uuid4().hex
    redis = create_sync_redis()
    deadline = time.monotonic() + _PLAYWRIGHT_BROWSER_LOCK_WAIT_S
    try:
        while time.monotonic() < deadline:
            if redis.set(
                _PLAYWRIGHT_BROWSER_LOCK_KEY,
                token,
                nx=True,
                ex=_PLAYWRIGHT_BROWSER_LOCK_TTL_S,
            ):
                logger.debug("playwright_browser_slot_acquired")
                return token
            time.sleep(_PLAYWRIGHT_BROWSER_LOCK_POLL_S)
    finally:
        redis.close()
    raise PlaywrightBrowserSlotTimeoutError(
        f"playwright browser slot unavailable after {_PLAYWRIGHT_BROWSER_LOCK_WAIT_S:.0f}s"
    )


def _release_playwright_browser_slot_sync(token: str) -> None:
    redis = create_sync_redis()
    try:
        redis.eval(_RELEASE_LOCK_SCRIPT, 1, _PLAYWRIGHT_BROWSER_LOCK_KEY, token)
        logger.debug("playwright_browser_slot_released")
    finally:
        redis.close()


@contextmanager
def playwright_browser_slot_sync() -> Iterator[None]:
    """Serialize Chromium usage across Celery workers/containers via Redis."""
    token = _acquire_playwright_browser_slot_sync()
    try:
        yield
    finally:
        _release_playwright_browser_slot_sync(token)


def launch_chromium_sync(playwright: Any, *, headless: bool) -> Any:
    """Launch Chromium with shared args and a bounded startup timeout."""
    return playwright.chromium.launch(
        headless=headless,
        args=list(CHROMIUM_LAUNCH_ARGS),
        timeout=_CHROMIUM_LAUNCH_TIMEOUT_MS,
    )


def dispose_sync_browser_context(context: Any | None, browser: Any | None) -> None:
    """Close browser context (and its pages) then browser; swallow errors so teardown completes."""
    if context is not None:
        with contextlib.suppress(Exception):
            context.close()
    if browser is not None:
        with contextlib.suppress(Exception):
            browser.close()
