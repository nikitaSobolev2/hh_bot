"""Shared Chromium launch options and teardown for sync Playwright runs."""

from __future__ import annotations

import contextlib
from typing import Any

# Docker: small /dev/shm causes Chromium crashes; headless Linux: drop GPU overhead.
CHROMIUM_LAUNCH_ARGS: tuple[str, ...] = (
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--no-first-run",
    "--no-default-browser-check",
)

# Fixed desktop viewport so Magritte bottom-sheet selectors match desktop layouts.
HH_UI_VIEWPORT: dict[str, int] = {"width": 1280, "height": 900}


def dispose_sync_browser_context(context: Any | None, browser: Any | None) -> None:
    """Close browser context (and its pages) then browser; swallow errors so teardown completes."""
    if context is not None:
        with contextlib.suppress(Exception):
            context.close()
    if browser is not None:
        with contextlib.suppress(Exception):
            browser.close()
