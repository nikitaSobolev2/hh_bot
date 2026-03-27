"""Popup-only apply path: no modal / no_apply_button when use_popup_api is True."""

from unittest.mock import MagicMock

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from src.services.hh_ui.config import HhUiApplyConfig
from src.services.hh_ui.outcomes import ApplyOutcome, ApplyResult
from src.services.hh_ui.runner import _apply_vacancy_flow_on_page
from src.services.hh_ui.vacancy_response_popup import (
    POPUP_INCOMPLETE_DETAIL,
    POPUP_XSRF_NOT_READY_DETAIL,
)


@pytest.fixture
def base_cfg() -> HhUiApplyConfig:
    return HhUiApplyConfig(
        headless=True,
        navigation_timeout_ms=10000,
        action_timeout_ms=5000,
        min_action_delay_ms=0,
        max_action_delay_ms=0,
        screenshot_on_error=False,
        use_popup_api=True,
        debug_screenshot_dir=None,
        attach_error_screenshot_bytes=False,
    )


def test_popup_only_returns_incomplete_when_try_popup_returns_none(
    monkeypatch, base_cfg: HhUiApplyConfig
) -> None:
    page = MagicMock()
    page.wait_for_selector = MagicMock(return_value=None)

    monkeypatch.setattr("src.services.hh_ui.runner._detect_login", lambda p: False)
    monkeypatch.setattr("src.services.hh_ui.runner._detect_captcha", lambda p: False)
    monkeypatch.setattr("src.services.hh_ui.runner._detect_already_applied", lambda p: False)
    monkeypatch.setattr(
        "src.services.hh_ui.runner.try_apply_via_popup",
        lambda *a, **k: None,
    )

    r = _apply_vacancy_flow_on_page(
        page,
        vacancy_url="https://hh.ru/vacancy/1",
        resume_hh_id="abc",
        config=base_cfg,
        log_user_id=1,
        cover_letter="",
    )
    assert r.outcome == ApplyOutcome.ERROR
    assert r.detail == POPUP_INCOMPLETE_DETAIL
    page.wait_for_selector.assert_called_once()


def test_popup_only_xsrf_wait_timeout_returns_not_ready(
    monkeypatch, base_cfg: HhUiApplyConfig
) -> None:
    page = MagicMock()
    page.wait_for_selector = MagicMock(
        side_effect=PlaywrightTimeoutError("timeout")
    )

    monkeypatch.setattr("src.services.hh_ui.runner._detect_login", lambda p: False)
    monkeypatch.setattr("src.services.hh_ui.runner._detect_captcha", lambda p: False)
    monkeypatch.setattr("src.services.hh_ui.runner._detect_already_applied", lambda p: False)
    monkeypatch.setattr(
        "src.services.hh_ui.runner.try_apply_via_popup",
        lambda *a, **k: pytest.fail("try_apply_via_popup must not run"),
    )

    r = _apply_vacancy_flow_on_page(
        page,
        vacancy_url="https://hh.ru/vacancy/1",
        resume_hh_id="abc",
        config=base_cfg,
        log_user_id=1,
        cover_letter="",
    )
    assert r.outcome == ApplyOutcome.ERROR
    assert r.detail == POPUP_XSRF_NOT_READY_DETAIL


def test_popup_path_returns_on_success(monkeypatch, base_cfg: HhUiApplyConfig) -> None:
    page = MagicMock()
    page.wait_for_selector = MagicMock(return_value=None)

    monkeypatch.setattr("src.services.hh_ui.runner._detect_login", lambda p: False)
    monkeypatch.setattr("src.services.hh_ui.runner._detect_captcha", lambda p: False)
    monkeypatch.setattr("src.services.hh_ui.runner._detect_already_applied", lambda p: False)
    monkeypatch.setattr(
        "src.services.hh_ui.runner.try_apply_via_popup",
        lambda *a, **k: ApplyResult(outcome=ApplyOutcome.SUCCESS, detail="popup_api"),
    )

    r = _apply_vacancy_flow_on_page(
        page,
        vacancy_url="https://hh.ru/vacancy/1",
        resume_hh_id="abc",
        config=base_cfg,
        log_user_id=1,
        cover_letter="",
    )
    assert r.outcome == ApplyOutcome.SUCCESS
