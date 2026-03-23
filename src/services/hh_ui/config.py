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

    @classmethod
    def from_settings(cls) -> HhUiApplyConfig:
        return cls(
            navigation_timeout_ms=int(settings.hh_ui_navigation_timeout_ms),
            action_timeout_ms=int(settings.hh_ui_action_timeout_ms),
            min_action_delay_ms=int(settings.hh_ui_min_action_delay_ms),
            max_action_delay_ms=int(settings.hh_ui_max_action_delay_ms),
            headless=bool(settings.hh_ui_headless),
            screenshot_on_error=bool(settings.hh_ui_screenshot_on_error),
        )
