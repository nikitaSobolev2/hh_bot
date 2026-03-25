"""Configuration for HH UI automation (Playwright)."""

from __future__ import annotations

from dataclasses import dataclass

from src.config import settings


@dataclass(frozen=True, slots=True)
class HhUiApplyConfig:
    navigation_timeout_ms: int
    action_timeout_ms: int
    min_action_delay_ms: int
    max_action_delay_ms: int
    headless: bool
    screenshot_on_error: bool
    use_popup_api: bool
    # When set, persist PNGs on error / failure outcomes (admin DB toggle + worker builds path).
    debug_screenshot_dir: str | None = None
    # When True, capture full-page PNG into ApplyResult.screenshot_bytes on error (for disk/Telegram).
    attach_error_screenshot_bytes: bool = False

    @classmethod
    def from_settings(cls) -> HhUiApplyConfig:
        return cls(
            navigation_timeout_ms=int(settings.hh_ui_navigation_timeout_ms),
            action_timeout_ms=int(settings.hh_ui_action_timeout_ms),
            min_action_delay_ms=int(settings.hh_ui_min_action_delay_ms),
            max_action_delay_ms=int(settings.hh_ui_max_action_delay_ms),
            headless=bool(settings.hh_ui_headless),
            screenshot_on_error=bool(settings.hh_ui_screenshot_on_error),
            use_popup_api=bool(settings.hh_ui_apply_use_popup_api),
            debug_screenshot_dir=None,
            attach_error_screenshot_bytes=False,
        )
