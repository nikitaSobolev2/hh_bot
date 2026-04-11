"""Sync Playwright runners for HH.ru resume list and vacancy apply."""

from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import Locator
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from src.core.logging import get_logger
from src.services.hh_ui import selectors as sel
from src.services.hh_ui.applicant_http import (
    fetch_applicant_resumes_html,
    html_suggests_captcha,
    html_suggests_login,
    parse_applicant_resumes_from_html,
    url_is_applicant_resumes_document,
    url_suggests_login_page,
)
from src.services.hh_ui.config import HhUiApplyConfig
from src.services.hh_ui.playwright_support import (
    CHROMIUM_LAUNCH_ARGS,
    HH_UI_VIEWPORT,
    dispose_sync_browser_context,
)
from src.services.hh_ui.vacancy_response_popup import (
    POPUP_INCOMPLETE_DETAIL,
    POPUP_XSRF_ERROR_DETAIL,
    POPUP_XSRF_NOT_READY_DETAIL,
    extract_xsrf_for_popup,
    is_negotiations_limit_popup_result,
    probe_xsrf_light_with_source,
    try_apply_via_popup,
)
from src.services.hh_ui.apply_retry import (
    apply_outcome_is_terminal_no_retry,
    apply_result_should_retry_popup_batch,
    apply_retry_delay_seconds,
)
from src.services.hh_ui.outcomes import ApplyOutcome, ApplyResult, ListResumesResult, ResumeOption

logger = get_logger(__name__)

_HH_UI_BATCH_XSRF_COOLDOWN_INITIAL_S = 10.0
_HH_UI_BATCH_XSRF_COOLDOWN_CAP_S = 300.0
# Chromium can crash under memory pressure; recover with a fresh browser instead of aborting the batch.
_HH_UI_BATCH_MAX_TARGET_CLOSED_RECOVERIES_PER_ITEM = 8
_XSRF_POLL_INTERVAL_S = 0.25
_XSRF_WAIT_CAP_MS = 15_000
_SEARCH_RESULTS_CARD_SELECTOR = '[data-qa="vacancy-serp__vacancy"]'


def _wait_for_xsrf_for_popup(
    page: Any, action_timeout_ms: int, log_user_id: int | None
) -> bool:
    """Wait until XSRF is available from DOM, ``_xsrf`` cookie, or HTML (no respond-button click)."""
    ms = min(int(action_timeout_ms), _XSRF_WAIT_CAP_MS)
    deadline = time.monotonic() + ms / 1000.0
    while time.monotonic() < deadline:
        _tok, src = probe_xsrf_light_with_source(page)
        if _tok and src:
            logger.info(
                "vacancy_popup_xsrf_ready",
                log_user_id=log_user_id,
                timeout_ms=ms,
                xsrf_source=src,
            )
            return True
        time.sleep(_XSRF_POLL_INTERVAL_S)
    if extract_xsrf_for_popup(page):
        logger.info(
            "vacancy_popup_xsrf_ready",
            log_user_id=log_user_id,
            timeout_ms=ms,
            xsrf_source="html",
        )
        return True
    logger.info(
        "vacancy_popup_xsrf_wait_timeout",
        log_user_id=log_user_id,
        timeout_ms=ms,
    )
    return False


def _is_popup_xsrf_error_result(result: ApplyResult) -> bool:
    return (result.detail or "").strip() == POPUP_XSRF_ERROR_DETAIL


def _safe_url_host_path(url: str | None) -> str | None:
    if not url or not isinstance(url, str):
        return None
    u = url.strip()
    if not u.startswith("https://"):
        return None
    try:
        p = urlparse(u)
        if not p.netloc:
            return None
        return f"{p.scheme}://{p.netloc}{p.path}"
    except Exception:
        return None


def _jitter(cfg: HhUiApplyConfig) -> None:
    lo = cfg.min_action_delay_ms / 1000.0
    hi = cfg.max_action_delay_ms / 1000.0
    if hi > 0 and hi >= lo:
        time.sleep(random.uniform(lo, hi))


def _maybe_screenshot(page: Any, cfg: HhUiApplyConfig) -> bytes | None:
    if not cfg.screenshot_on_error:
        return None
    try:
        return page.screenshot(type="png")
    except Exception:
        return None


def _maybe_embed_popup_error_screenshot(
    config: HhUiApplyConfig,
    page: Any,
    result: ApplyResult,
) -> ApplyResult:
    """Attach full-page PNG to ApplyResult for disk/Telegram when admin enables attach_error_screenshot_bytes."""
    if not config.attach_error_screenshot_bytes:
        return result
    if result.screenshot_bytes:
        return result
    if result.outcome == ApplyOutcome.CAPTCHA:
        return result
    if result.outcome not in _DEBUG_SAVE_OUTCOMES:
        return result
    try:
        shot = _screenshot_page_captcha(page)
        if shot:
            return replace(result, screenshot_bytes=shot)
    except Exception:
        pass
    return result


_DEBUG_SAVE_OUTCOMES = frozenset(
    {
        ApplyOutcome.ERROR,
        ApplyOutcome.NO_APPLY_BUTTON,
        ApplyOutcome.SESSION_EXPIRED,
        ApplyOutcome.CAPTCHA,
        ApplyOutcome.EMPLOYER_QUESTIONS,
        ApplyOutcome.RATE_LIMITED,
    }
)


def _save_playwright_debug_disk(
    config: HhUiApplyConfig,
    *,
    page: Any | None,
    result: ApplyResult,
    stem: str,
) -> None:
    """Persist PNG when admin enables debug and outcome is a failure class."""
    if not config.debug_screenshot_dir:
        return
    if result.outcome not in _DEBUG_SAVE_OUTCOMES:
        return
    try:
        root = Path(config.debug_screenshot_dir)
        root.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S_%f")
        safe = re.sub(r"[^\w.-]+", "_", stem)[:120]
        dest = root / f"{ts}_{safe}.png"
        if result.screenshot_bytes:
            dest.write_bytes(result.screenshot_bytes)
        elif page is not None:
            page.screenshot(path=str(dest), type="png", full_page=True)
        logger.info(
            "playwright_debug_screenshot_saved",
            path=str(dest),
            outcome=result.outcome.value,
            stem=stem[:80],
        )
    except Exception as exc:
        logger.warning(
            "playwright_debug_screenshot_failed",
            stem=stem[:80],
            error=str(exc)[:200],
        )


def _screenshot_page_captcha(page: Any) -> bytes | None:
    """Always capture the page when captcha is shown (not gated by screenshot_on_error)."""
    try:
        return page.screenshot(type="png", full_page=True)
    except Exception:
        return None


@dataclass(frozen=True)
class SearchPageRenderResult:
    html: str | None
    final_url: str | None
    cards_before_scroll: int
    cards_after_scroll: int
    error: str | None = None


def _count_search_cards(page: Any) -> int:
    try:
        return int(page.locator(_SEARCH_RESULTS_CARD_SELECTOR).count())
    except Exception:
        return 0


def render_search_page_with_storage(
    *,
    storage_state: dict[str, Any] | None,
    config: HhUiApplyConfig,
    url: str,
    log_user_id: int | None = None,
) -> SearchPageRenderResult:
    """Open HH search page in Chromium, scroll once, and return rendered HTML."""
    logger.info(
        "render_search_page_start",
        log_user_id=log_user_id,
        url=url,
        has_storage=bool(storage_state),
    )
    with sync_playwright() as p:
        browser = None
        context = None
        try:
            browser = p.chromium.launch(
                headless=config.headless,
                args=list(CHROMIUM_LAUNCH_ARGS),
            )
            context_kwargs: dict[str, Any] = {"viewport": HH_UI_VIEWPORT}
            if storage_state:
                context_kwargs["storage_state"] = storage_state
            context = browser.new_context(**context_kwargs)
            page = context.new_page()
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=config.navigation_timeout_ms,
            )
            try:
                page.locator(_SEARCH_RESULTS_CARD_SELECTOR).first.wait_for(
                    state="attached",
                    timeout=min(config.action_timeout_ms, config.navigation_timeout_ms),
                )
            except Exception:
                pass
            _jitter(config)
            cards_before = _count_search_cards(page)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(max(config.min_action_delay_ms, 1000))
            cards_after = _count_search_cards(page)
            final_url = page.url
            logger.info(
                "render_search_page_done",
                log_user_id=log_user_id,
                url=url,
                final_url=final_url,
                has_storage=bool(storage_state),
                cards_before_scroll=cards_before,
                cards_after_scroll=cards_after,
                login_detected=url_suggests_login_page(final_url),
                captcha_detected=_detect_captcha(page),
            )
            return SearchPageRenderResult(
                html=page.content(),
                final_url=final_url,
                cards_before_scroll=cards_before,
                cards_after_scroll=cards_after,
            )
        except PlaywrightTimeoutError as exc:
            logger.warning(
                "render_search_page_timeout",
                log_user_id=log_user_id,
                url=url,
                has_storage=bool(storage_state),
                error=str(exc)[:200],
            )
            return SearchPageRenderResult(
                html=None,
                final_url=None,
                cards_before_scroll=0,
                cards_after_scroll=0,
                error="timeout",
            )
        except Exception as exc:
            logger.warning(
                "render_search_page_failed",
                log_user_id=log_user_id,
                url=url,
                has_storage=bool(storage_state),
                error=str(exc)[:200],
            )
            return SearchPageRenderResult(
                html=None,
                final_url=None,
                cards_before_scroll=0,
                cards_after_scroll=0,
                error=str(exc)[:200],
            )
        finally:
            dispose_sync_browser_context(context, browser)


def _screenshot_url_with_storage(
    storage_state: dict[str, Any],
    config: HhUiApplyConfig,
    url: str,
) -> bytes | None:
    """Open Chromium with the same Playwright storage_state and screenshot (e.g. HTTP-detected captcha)."""
    with sync_playwright() as p:
        browser = None
        context = None
        try:
            browser = p.chromium.launch(
                headless=config.headless,
                args=list(CHROMIUM_LAUNCH_ARGS),
            )
            context = browser.new_context(
                storage_state=storage_state,
                viewport=HH_UI_VIEWPORT,
            )
            page = context.new_page()
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=config.navigation_timeout_ms,
            )
            _jitter(config)
            return _screenshot_page_captcha(page)
        except Exception:
            return None
        finally:
            dispose_sync_browser_context(context, browser)


def _detect_captcha(page: Any) -> bool:
    """Detect visible captcha widgets only — not bare \"smartcaptcha\" in page HTML/JSON."""
    for hint in sel.CAPTCHA_HINTS:
        try:
            if page.locator(hint).count() > 0:
                return True
        except Exception:
            continue
    return False


def _detect_login(page: Any) -> bool:
    for hint in sel.LOGIN_FORM:
        try:
            if page.locator(hint).count() > 0:
                return True
        except Exception:
            continue
    u = (page.url or "").lower()
    return "/account/login" in u or "/account/signup" in u


def _detect_already_applied(page: Any) -> bool:
    for hint in sel.ALREADY_APPLIED_HINTS:
        try:
            if page.locator(hint).count() > 0:
                return True
        except Exception:
            continue
    return False


def _detect_employer_questions(page: Any) -> bool:
    for hint in sel.EMPLOYER_QUESTION_HINTS:
        try:
            if page.locator(hint).count() > 0:
                return True
        except Exception:
            continue
    return False


def _fill_cover_letter_if_present(
    page: Any,
    cover_letter: str,
    action_timeout_ms: int,
    log_user_id: int | None,
) -> None:
    """Best-effort fill cover letter textarea in respond modal; never logs letter body."""
    text = (cover_letter or "").strip()
    if not text:
        return
    to_try: list[Any] = []
    modal = page.locator(sel.RESPONSE_MODAL_CONTENT).first
    try:
        if modal.count() > 0:
            to_try.append(modal)
    except Exception:
        pass
    to_try.append(page)
    for root in to_try:
        for s in sel.RESPONSE_LETTER_TEXTAREA:
            loc = root.locator(s).first
            try:
                loc.wait_for(state="attached", timeout=min(4000, action_timeout_ms))
                loc.fill(text)
                logger.info(
                    "apply_to_vacancy_ui_step",
                    log_user_id=log_user_id,
                    step="cover_letter_filled",
                    letter_selector=s,
                )
                return
            except Exception:
                continue
    logger.info(
        "apply_to_vacancy_ui_step",
        log_user_id=log_user_id,
        step="cover_letter_field_not_found",
    )


def _click_first(page: Any, selectors: tuple[str, ...], timeout: int) -> bool:
    for s in selectors:
        loc = page.locator(s).first
        try:
            loc.wait_for(state="visible", timeout=timeout)
            loc.click()
            return True
        except PlaywrightTimeoutError:
            continue
    return False


def _click_first_in_root(root: Locator, selectors: tuple[str, ...], timeout: int) -> bool:
    for s in selectors:
        loc = root.locator(s).first
        try:
            loc.wait_for(state="visible", timeout=timeout)
            loc.click()
            return True
        except PlaywrightTimeoutError:
            continue
    return False


def _wait_for_respond_resume_ui(page: Any, timeout_ms: int) -> None:
    """Wait until resume picker appears: radios (preferred), bottom sheet, or sheet container."""
    radio = page.locator('input[name="resumeId"]').first
    sheet_content = page.locator(sel.RESPONSE_MODAL_CONTENT).first
    sheet_outer = page.locator(sel.BOTTOM_SHEET_CONTAINER).first
    radio.or_(sheet_content).or_(sheet_outer).wait_for(state="visible", timeout=timeout_ms)


def list_resumes_ui(
    *,
    storage_state: dict[str, Any],
    config: HhUiApplyConfig,
    log_user_id: int | None = None,
) -> ListResumesResult:
    """Load applicant resume list via HTTP GET + HTML parse (session cookies from storage_state)."""
    logger.info(
        "list_resumes_ui_start",
        log_user_id=log_user_id,
        branch="applicant",
    )
    html, fetch_err, final_url = fetch_applicant_resumes_html(storage_state, config)
    if fetch_err or not html:
        detail = fetch_err or "empty_response"
        logger.info(
            "list_resumes_ui_done",
            log_user_id=log_user_id,
            branch="applicant",
            resume_count=0,
            outcome=ApplyOutcome.ERROR.value,
            detail=detail,
        )
        return ListResumesResult(
            resumes=[],
            outcome=ApplyOutcome.ERROR,
            detail=detail,
        )
    if final_url and url_suggests_login_page(final_url):
        logger.info(
            "list_resumes_ui_done",
            log_user_id=log_user_id,
            branch="applicant",
            resume_count=0,
            outcome=ApplyOutcome.SESSION_EXPIRED.value,
            detail="login_redirect",
        )
        return ListResumesResult(
            resumes=[],
            outcome=ApplyOutcome.SESSION_EXPIRED,
            detail="login_redirect",
        )
    # On /applicant/resumes, HH often embeds footer links to account/login — html heuristics lie.
    if (not final_url or not url_is_applicant_resumes_document(final_url)) and html_suggests_login(
        html
    ):
        logger.info(
            "list_resumes_ui_done",
            log_user_id=log_user_id,
            branch="applicant",
            resume_count=0,
            outcome=ApplyOutcome.SESSION_EXPIRED.value,
            detail="login_form",
        )
        return ListResumesResult(
            resumes=[],
            outcome=ApplyOutcome.SESSION_EXPIRED,
            detail="login_form",
        )
    if html_suggests_captcha(html):
        captcha_shot = _screenshot_url_with_storage(
            storage_state, config, sel.APPLICANT_RESUMES_URL
        )
        logger.info(
            "list_resumes_ui_done",
            log_user_id=log_user_id,
            branch="applicant",
            resume_count=0,
            outcome=ApplyOutcome.CAPTCHA.value,
            detail="captcha",
        )
        return ListResumesResult(
            resumes=[],
            outcome=ApplyOutcome.CAPTCHA,
            detail="captcha",
            screenshot_bytes=captcha_shot,
        )
    result = parse_applicant_resumes_from_html(html)
    logger.info(
        "list_resumes_ui_done",
        log_user_id=log_user_id,
        branch="applicant",
        resume_count=len(result.resumes),
        outcome=result.outcome.value,
        detail=result.detail,
    )
    return result


def apply_to_vacancy_ui(
    *,
    storage_state: dict[str, Any],
    vacancy_url: str,
    resume_hh_id: str,
    config: HhUiApplyConfig,
    log_user_id: int | None = None,
    cover_letter: str = "",
) -> ApplyResult:
    """Open vacancy page and submit respond via UI."""
    safe_v = _safe_url_host_path(vacancy_url)
    resume_ref = resume_hh_id[:12] if resume_hh_id else None
    if not vacancy_url.startswith("https://"):
        logger.info(
            "apply_to_vacancy_ui_done",
            log_user_id=log_user_id,
            step="validate_url",
            vacancy_url_safe=safe_v,
            resume_ref=resume_ref,
            outcome=ApplyOutcome.ERROR.value,
            detail="invalid_vacancy_url",
        )
        return ApplyResult(
            outcome=ApplyOutcome.ERROR,
            detail="invalid_vacancy_url",
        )

    with sync_playwright() as p:
        browser = None
        context = None
        try:
            browser = p.chromium.launch(
                headless=config.headless,
                args=list(CHROMIUM_LAUNCH_ARGS),
            )
            context = browser.new_context(
                storage_state=storage_state,
                viewport=HH_UI_VIEWPORT,
            )
            page = context.new_page()
            page.goto(
                vacancy_url,
                wait_until="domcontentloaded",
                timeout=config.navigation_timeout_ms,
            )
            _jitter(config)
            return _apply_vacancy_flow_on_page(
                page,
                vacancy_url=vacancy_url,
                resume_hh_id=resume_hh_id,
                config=config,
                log_user_id=log_user_id,
                cover_letter=cover_letter,
            )
        except PlaywrightTimeoutError as exc:
            logger.info(
                "apply_to_vacancy_ui_done",
                log_user_id=log_user_id,
                vacancy_url_safe=safe_v,
                resume_ref=resume_ref,
                outcome=ApplyOutcome.ERROR.value,
                detail=f"timeout:{exc}"[:200],
            )
            r = ApplyResult(
                outcome=ApplyOutcome.ERROR,
                detail=f"timeout:{exc}",
            )
            _save_playwright_debug_disk(
                config,
                page=locals().get("page"),
                result=r,
                stem="playwright_timeout",
            )
            return r
        except Exception as exc:
            d = str(exc)[:500]
            logger.info(
                "apply_to_vacancy_ui_done",
                log_user_id=log_user_id,
                vacancy_url_safe=safe_v,
                resume_ref=resume_ref,
                outcome=ApplyOutcome.ERROR.value,
                detail=d[:200],
            )
            r = ApplyResult(
                outcome=ApplyOutcome.ERROR,
                detail=d,
            )
            _save_playwright_debug_disk(
                config,
                page=locals().get("page"),
                result=r,
                stem="playwright_exception",
            )
            return r
        finally:
            dispose_sync_browser_context(context, browser)


def _apply_vacancy_flow_on_page(
    page: Any,
    *,
    vacancy_url: str,
    resume_hh_id: str,
    config: HhUiApplyConfig,
    log_user_id: int | None,
    cover_letter: str,
) -> ApplyResult:
    """Run respond flow after ``page`` has navigated to the vacancy (and optional jitter)."""
    safe_v = _safe_url_host_path(vacancy_url)
    resume_ref = resume_hh_id[:12] if resume_hh_id else None
    logger.info(
        "apply_to_vacancy_ui_step",
        log_user_id=log_user_id,
        step="after_goto",
        vacancy_url_safe=safe_v,
        resume_ref=resume_ref,
    )

    def _finish(result: ApplyResult, stem: str) -> ApplyResult:
        _save_playwright_debug_disk(config, page=page, result=result, stem=stem)
        return result

    try:
        if _detect_login(page):
            logger.info(
                "apply_to_vacancy_ui_done",
                log_user_id=log_user_id,
                vacancy_url_safe=safe_v,
                resume_ref=resume_ref,
                outcome=ApplyOutcome.SESSION_EXPIRED.value,
                detail="login_form",
            )
            return _finish(
                ApplyResult(
                    outcome=ApplyOutcome.SESSION_EXPIRED,
                    detail="login_form",
                ),
                "login_form",
            )
        if _detect_captcha(page):
            shot = _screenshot_page_captcha(page)
            logger.info(
                "apply_to_vacancy_ui_done",
                log_user_id=log_user_id,
                vacancy_url_safe=safe_v,
                resume_ref=resume_ref,
                outcome=ApplyOutcome.CAPTCHA.value,
                detail="captcha",
            )
            return _finish(
                ApplyResult(
                    outcome=ApplyOutcome.CAPTCHA,
                    detail="captcha",
                    screenshot_bytes=shot,
                ),
                "captcha_initial",
            )

        if _detect_already_applied(page):
            logger.info(
                "apply_to_vacancy_ui_done",
                log_user_id=log_user_id,
                vacancy_url_safe=safe_v,
                resume_ref=resume_ref,
                outcome=ApplyOutcome.ALREADY_RESPONDED.value,
                detail=None,
            )
            return _finish(
                ApplyResult(outcome=ApplyOutcome.ALREADY_RESPONDED),
                "already_applied_initial",
            )

        if config.use_popup_api:
            logger.info(
                "apply_to_vacancy_ui_step",
                log_user_id=log_user_id,
                step="before_popup_api",
                vacancy_url_safe=safe_v,
                resume_ref=resume_ref,
            )
            if not _wait_for_xsrf_for_popup(
                page, config.action_timeout_ms, log_user_id
            ):
                logger.info(
                    "apply_to_vacancy_ui_done",
                    log_user_id=log_user_id,
                    vacancy_url_safe=safe_v,
                    resume_ref=resume_ref,
                    outcome=ApplyOutcome.ERROR.value,
                    detail=POPUP_XSRF_NOT_READY_DETAIL,
                )
                return _finish(
                    ApplyResult(
                        outcome=ApplyOutcome.ERROR,
                        detail=POPUP_XSRF_NOT_READY_DETAIL,
                    ),
                    "popup_api_xsrf_not_ready",
                )
            popup_result = try_apply_via_popup(
                page,
                vacancy_url,
                resume_hh_id,
                log_user_id=log_user_id,
                letter=cover_letter or "",
            )
            if popup_result is not None:
                popup_result = _maybe_embed_popup_error_screenshot(
                    config, page, popup_result
                )
                logger.info(
                    "apply_to_vacancy_ui_done",
                    log_user_id=log_user_id,
                    step="popup_api",
                    vacancy_url_safe=safe_v,
                    resume_ref=resume_ref,
                    outcome=popup_result.outcome.value,
                    detail=(popup_result.detail or "")[:200] if popup_result.detail else None,
                )
                return _finish(popup_result, "popup_api")
            logger.info(
                "apply_to_vacancy_ui_done",
                log_user_id=log_user_id,
                step="popup_api_incomplete",
                vacancy_url_safe=safe_v,
                resume_ref=resume_ref,
                outcome=ApplyOutcome.ERROR.value,
                detail=POPUP_INCOMPLETE_DETAIL,
            )
            return _finish(
                ApplyResult(
                    outcome=ApplyOutcome.ERROR,
                    detail=POPUP_INCOMPLETE_DETAIL,
                ),
                "popup_api_incomplete",
            )

        logger.info(
            "apply_to_vacancy_ui_step",
            log_user_id=log_user_id,
            step="modal_apply_flow",
            vacancy_url_safe=safe_v,
            resume_ref=resume_ref,
        )

        if not _click_first(
            page,
            sel.VACANCY_APPLY_BUTTON,
            min(2000, config.action_timeout_ms),
        ):
            shot = _maybe_screenshot(page, config)
            logger.info(
                "apply_to_vacancy_ui_done",
                log_user_id=log_user_id,
                vacancy_url_safe=safe_v,
                resume_ref=resume_ref,
                outcome=ApplyOutcome.NO_APPLY_BUTTON.value,
                detail="no_apply_button",
            )
            return _finish(
                ApplyResult(
                    outcome=ApplyOutcome.NO_APPLY_BUTTON,
                    detail="no_apply_button",
                    screenshot_bytes=shot,
                ),
                "no_apply_button",
            )

        _jitter(config)
        page.wait_for_timeout(500)
        logger.info(
            "apply_to_vacancy_ui_step",
            log_user_id=log_user_id,
            step="after_respond_click",
            vacancy_url_safe=safe_v,
            resume_ref=resume_ref,
        )

        if _detect_already_applied(page):
            logger.info(
                "apply_to_vacancy_ui_done",
                log_user_id=log_user_id,
                vacancy_url_safe=safe_v,
                resume_ref=resume_ref,
                outcome=ApplyOutcome.ALREADY_RESPONDED.value,
                detail=None,
            )
            return _finish(
                ApplyResult(outcome=ApplyOutcome.ALREADY_RESPONDED),
                "already_applied_after_click",
            )

        if _detect_employer_questions(page):
            logger.info(
                "apply_to_vacancy_ui_done",
                log_user_id=log_user_id,
                vacancy_url_safe=safe_v,
                resume_ref=resume_ref,
                outcome=ApplyOutcome.EMPLOYER_QUESTIONS.value,
                detail="employer_questions",
            )
            return _finish(
                ApplyResult(
                    outcome=ApplyOutcome.EMPLOYER_QUESTIONS,
                    detail="employer_questions",
                ),
                "employer_questions",
            )

        if _detect_captcha(page):
            shot = _screenshot_page_captcha(page)
            logger.info(
                "apply_to_vacancy_ui_done",
                log_user_id=log_user_id,
                vacancy_url_safe=safe_v,
                resume_ref=resume_ref,
                outcome=ApplyOutcome.CAPTCHA.value,
                detail="captcha_after_click",
            )
            return _finish(
                ApplyResult(
                    outcome=ApplyOutcome.CAPTCHA,
                    detail="captcha_after_click",
                    screenshot_bytes=shot,
                ),
                "captcha_after_click",
            )

        selected = False
        modal_visible = False
        try:
            _wait_for_respond_resume_ui(page, config.action_timeout_ms)
            modal_visible = True
        except PlaywrightTimeoutError:
            pass
        logger.info(
            "apply_to_vacancy_ui_step",
            log_user_id=log_user_id,
            step="response_modal",
            modal_visible=modal_visible,
            vacancy_url_safe=safe_v,
            resume_ref=resume_ref,
        )
        page.wait_for_timeout(400)
        select_mode = "none"

        # Target resume already selected (multi-resume bottom sheet).
        if not selected:
            try:
                checked = page.locator(
                    f'input[name="resumeId"][value="{resume_hh_id}"]:checked'
                ).first
                checked.wait_for(
                    state="attached",
                    timeout=min(3000, config.action_timeout_ms),
                )
                selected = True
                select_mode = "pre_checked"
            except Exception:
                pass

        # Single resume row — value must match; check if needed.
        if not selected:
            try:
                radios = page.locator('input[name="resumeId"]')
                if radios.count() == 1:
                    one = radios.first
                    one.wait_for(state="attached", timeout=config.action_timeout_ms)
                    if (one.get_attribute("value") or "") == resume_hh_id:
                        one.scroll_into_view_if_needed()
                        if not one.is_checked():
                            one.check(force=True)
                        selected = True
                        select_mode = "single_resume"
            except Exception:
                pass

        # Always try resume selection even if sheet wait failed (layout may still expose radios).
        if not selected:
            try:
                radio = page.locator(f'input[name="resumeId"][value="{resume_hh_id}"]').first
                radio.wait_for(state="attached", timeout=config.action_timeout_ms)
                radio.scroll_into_view_if_needed()
                radio.check(force=True)
                selected = True
                select_mode = "radio"
            except Exception:
                try:
                    lbl = page.locator(
                        f'label:has(input[name="resumeId"][value="{resume_hh_id}"])'
                    ).first
                    lbl.wait_for(state="visible", timeout=config.action_timeout_ms)
                    lbl.scroll_into_view_if_needed()
                    lbl.click(force=True)
                    selected = True
                    select_mode = "label"
                except Exception:
                    pass

        if not selected:
            for s in sel.RESUME_SELECT:
                loc = page.locator(s).first
                try:
                    loc.wait_for(state="visible", timeout=config.action_timeout_ms)
                    loc.scroll_into_view_if_needed()
                    loc.select_option(value=resume_hh_id)
                    selected = True
                    select_mode = "select"
                    break
                except Exception:
                    continue

        if not selected:
            card = page.locator(f'a[data-qa="resume-card-link-{resume_hh_id}"]').first
            try:
                card.wait_for(state="visible", timeout=config.action_timeout_ms)
                card.scroll_into_view_if_needed()
                card.click()
                selected = True
                select_mode = "resume_card"
            except Exception:
                pass

        if not selected:
            alt = page.locator(f'a[href*="/resume/{resume_hh_id}"]').first
            try:
                alt.wait_for(state="visible", timeout=config.action_timeout_ms)
                alt.scroll_into_view_if_needed()
                alt.click()
                selected = True
                select_mode = "link"
            except Exception:
                pass

        if not selected:
            shot = _maybe_screenshot(page, config)
            logger.info(
                "apply_to_vacancy_ui_done",
                log_user_id=log_user_id,
                vacancy_url_safe=safe_v,
                resume_ref=resume_ref,
                outcome=ApplyOutcome.ERROR.value,
                detail="resume_not_selectable",
            )
            return _finish(
                ApplyResult(
                    outcome=ApplyOutcome.ERROR,
                    detail="resume_not_selectable",
                    screenshot_bytes=shot,
                ),
                "resume_not_selectable",
            )

        logger.info(
            "apply_to_vacancy_ui_step",
            log_user_id=log_user_id,
            step="resume_selected",
            select_mode=select_mode,
            vacancy_url_safe=safe_v,
            resume_ref=resume_ref,
        )

        _jitter(config)
        _fill_cover_letter_if_present(page, cover_letter, config.action_timeout_ms, log_user_id)

        modal_root = page.locator(sel.RESPONSE_MODAL_CONTENT).first
        submitted = False
        submit_where = "none"
        try:
            if modal_root.is_visible():
                submitted = _click_first_in_root(
                    modal_root,
                    sel.RESUME_SUBMIT,
                    config.action_timeout_ms,
                )
                if submitted:
                    submit_where = "modal"
        except Exception:
            pass
        if not submitted:
            submitted = _click_first(
                page,
                sel.RESUME_SUBMIT,
                config.action_timeout_ms,
            )
            if submitted:
                submit_where = "page"
        if not submitted:
            shot = _maybe_screenshot(page, config)
            logger.info(
                "apply_to_vacancy_ui_done",
                log_user_id=log_user_id,
                vacancy_url_safe=safe_v,
                resume_ref=resume_ref,
                outcome=ApplyOutcome.ERROR.value,
                detail="submit_not_found",
            )
            return _finish(
                ApplyResult(
                    outcome=ApplyOutcome.ERROR,
                    detail="submit_not_found",
                    screenshot_bytes=shot,
                ),
                "submit_not_found",
            )

        logger.info(
            "apply_to_vacancy_ui_step",
            log_user_id=log_user_id,
            step="after_submit",
            submit_where=submit_where,
            vacancy_url_safe=safe_v,
            resume_ref=resume_ref,
        )

        _jitter(config)
        page.wait_for_timeout(500)

        if _detect_already_applied(page):
            logger.info(
                "apply_to_vacancy_ui_done",
                log_user_id=log_user_id,
                vacancy_url_safe=safe_v,
                resume_ref=resume_ref,
                outcome=ApplyOutcome.ALREADY_RESPONDED.value,
                detail=None,
            )
            return _finish(
                ApplyResult(outcome=ApplyOutcome.ALREADY_RESPONDED),
                "already_applied_after_submit",
            )

        if _detect_employer_questions(page):
            logger.info(
                "apply_to_vacancy_ui_done",
                log_user_id=log_user_id,
                vacancy_url_safe=safe_v,
                resume_ref=resume_ref,
                outcome=ApplyOutcome.EMPLOYER_QUESTIONS.value,
                detail="employer_questions_after_submit",
            )
            return _finish(
                ApplyResult(
                    outcome=ApplyOutcome.EMPLOYER_QUESTIONS,
                    detail="employer_questions_after_submit",
                ),
                "employer_questions_after_submit",
            )

        logger.info(
            "apply_to_vacancy_ui_done",
            log_user_id=log_user_id,
            vacancy_url_safe=safe_v,
            resume_ref=resume_ref,
            outcome=ApplyOutcome.SUCCESS.value,
            detail=None,
        )
        return _finish(ApplyResult(outcome=ApplyOutcome.SUCCESS), "success")
    except PlaywrightTimeoutError as exc:
        logger.info(
            "apply_to_vacancy_ui_done",
            log_user_id=log_user_id,
            vacancy_url_safe=safe_v,
            resume_ref=resume_ref,
            outcome=ApplyOutcome.ERROR.value,
            detail=f"timeout:{exc}"[:200],
        )
        r = ApplyResult(
            outcome=ApplyOutcome.ERROR,
            detail=f"timeout:{exc}",
        )
        _save_playwright_debug_disk(
            config,
            page=page,
            result=r,
            stem="playwright_timeout",
        )
        return r
    except Exception as exc:
        d = str(exc)[:500]
        logger.info(
            "apply_to_vacancy_ui_done",
            log_user_id=log_user_id,
            vacancy_url_safe=safe_v,
            resume_ref=resume_ref,
            outcome=ApplyOutcome.ERROR.value,
            detail=d[:200],
        )
        r = ApplyResult(
            outcome=ApplyOutcome.ERROR,
            detail=d,
        )
        _save_playwright_debug_disk(
            config,
            page=page,
            result=r,
            stem="playwright_exception",
        )
        return r




def _is_target_closed_error(exc: BaseException) -> bool:
    """True when Playwright page/context/browser died (crash or explicit close)."""
    name = type(exc).__name__
    if "TargetClosed" in name or "BrowserClosed" in name:
        return True
    msg = str(exc).lower()
    return "has been closed" in msg or "target closed" in msg or "browser has been closed" in msg


def _is_page_goto_timeout_error(exc: BaseException) -> bool:
    """Navigation timeout (slow host or overloaded worker)."""
    return isinstance(exc, PlaywrightTimeoutError)


def _launch_batch_browser_session(
    playwright: Any,
    storage_state: dict[str, Any],
    config: HhUiApplyConfig,
) -> tuple[Any, Any, Any]:
    """New Chromium + context + page for :func:`apply_to_vacancies_ui_batch`."""
    browser = playwright.chromium.launch(
        headless=config.headless,
        args=list(CHROMIUM_LAUNCH_ARGS),
    )
    context = browser.new_context(
        storage_state=storage_state,
        viewport=HH_UI_VIEWPORT,
    )
    page = context.new_page()
    return browser, context, page


@dataclass(frozen=True)
class VacancyApplySpec:
    """One vacancy in a UI apply batch (same browser session)."""

    autoparsed_vacancy_id: int
    hh_vacancy_id: str
    vacancy_url: str
    resume_hh_id: str
    cover_letter: str


def apply_to_vacancies_ui_batch(
    *,
    storage_state: dict[str, Any],
    items: list[VacancyApplySpec],
    config: HhUiApplyConfig,
    log_user_id: int | None = None,
    max_retries: int = 5,
    retry_initial_seconds: float = 10.0,
    retry_delay_cap_seconds: float = 600.0,
    on_item_done: Callable[[VacancyApplySpec, ApplyResult], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    xsrf_cooldown_initial_seconds: float = _HH_UI_BATCH_XSRF_COOLDOWN_INITIAL_S,
    xsrf_cooldown_cap_seconds: float = _HH_UI_BATCH_XSRF_COOLDOWN_CAP_S,
) -> tuple[list[tuple[int, ApplyResult]], str | None]:
    """Sequential ``goto`` + apply per item in one browser session; retries with backoff per item.

    If Chromium crashes or the page target closes (OOM, ``Target crashed``), launches a fresh
    browser with the same ``storage_state`` and retries the current attempt (capped per vacancy).

    Returns ``(results, abort_reason)``. ``abort_reason`` is ``\"negotiations_limit\"``,
    ``\"cancelled\"``, or ``None`` when the loop finished normally.
    """
    results: list[tuple[int, ApplyResult]] = []
    if not items:
        return results, None

    with sync_playwright() as p:
        browser = None
        context = None
        try:
            browser, context, page = _launch_batch_browser_session(p, storage_state, config)
            consecutive_popup_xsrf = 0
            for item_index, spec in enumerate(items):
                if cancel_check and cancel_check():
                    return results, "cancelled"
                if not spec.vacancy_url.startswith("https://"):
                    invalid = ApplyResult(
                        outcome=ApplyOutcome.ERROR,
                        detail="invalid_vacancy_url",
                    )
                    if on_item_done:
                        on_item_done(spec, invalid)
                    results.append((spec.autoparsed_vacancy_id, invalid))
                    continue
                last: ApplyResult | None = None
                attempt = 0
                target_closed_recoveries = 0
                while attempt < max_retries:
                    try:
                        page.goto(
                            spec.vacancy_url,
                            wait_until="domcontentloaded",
                            timeout=config.navigation_timeout_ms,
                        )
                        _jitter(config)
                        last = _apply_vacancy_flow_on_page(
                            page,
                            vacancy_url=spec.vacancy_url,
                            resume_hh_id=spec.resume_hh_id,
                            config=config,
                            log_user_id=log_user_id,
                            cover_letter=spec.cover_letter,
                        )
                    except Exception as exc:
                        if _is_page_goto_timeout_error(exc):
                            logger.warning(
                                "hh_ui_batch_goto_timeout",
                                log_user_id=log_user_id,
                                vacancy_id=spec.autoparsed_vacancy_id,
                                url=spec.vacancy_url[:120],
                                attempt=attempt + 1,
                                max_retries=max_retries,
                                error=str(exc)[:300],
                            )
                            attempt += 1
                            if attempt < max_retries:
                                delay = apply_retry_delay_seconds(
                                    attempt - 1,
                                    retry_initial_seconds,
                                    retry_delay_cap_seconds,
                                )
                                time.sleep(delay)
                                continue
                            last = ApplyResult(
                                outcome=ApplyOutcome.ERROR,
                                detail="page_goto_timeout",
                            )
                            break
                        if not _is_target_closed_error(exc):
                            raise
                        target_closed_recoveries += 1
                        if target_closed_recoveries > _HH_UI_BATCH_MAX_TARGET_CLOSED_RECOVERIES_PER_ITEM:
                            logger.error(
                                "hh_ui_batch_target_closed_recoveries_exhausted",
                                log_user_id=log_user_id,
                                vacancy_id=spec.autoparsed_vacancy_id,
                                recoveries=target_closed_recoveries,
                                error=str(exc)[:400],
                            )
                            last = ApplyResult(
                                outcome=ApplyOutcome.ERROR,
                                detail=f"browser_target_closed:{target_closed_recoveries}",
                            )
                            break
                        logger.warning(
                            "hh_ui_batch_target_closed_recovering",
                            log_user_id=log_user_id,
                            vacancy_id=spec.autoparsed_vacancy_id,
                            apply_attempt=attempt + 1,
                            recovery_n=target_closed_recoveries,
                            error=str(exc)[:400],
                        )
                        dispose_sync_browser_context(context, browser)
                        browser, context, page = _launch_batch_browser_session(
                            p, storage_state, config
                        )
                        continue
                    if last is None:
                        last = ApplyResult(outcome=ApplyOutcome.ERROR, detail="empty")
                    if apply_outcome_is_terminal_no_retry(last.outcome):
                        break
                    if not apply_result_should_retry_popup_batch(last):
                        break
                    if attempt < max_retries - 1:
                        delay = apply_retry_delay_seconds(
                            attempt, retry_initial_seconds, retry_delay_cap_seconds
                        )
                        logger.info(
                            "hh_ui_apply_batch_retry",
                            log_user_id=log_user_id,
                            vacancy_id=spec.autoparsed_vacancy_id,
                            attempt=attempt + 1,
                            outcome=last.outcome.value,
                            next_delay_s=delay,
                        )
                        time.sleep(delay)
                    attempt += 1
                final = last or ApplyResult(outcome=ApplyOutcome.ERROR, detail="empty")
                if on_item_done:
                    on_item_done(spec, final)
                results.append((spec.autoparsed_vacancy_id, final))
                if is_negotiations_limit_popup_result(final):
                    return results, "negotiations_limit"
                if item_index < len(items) - 1 and _is_popup_xsrf_error_result(final):
                    consecutive_popup_xsrf += 1
                    delay = min(
                        float(xsrf_cooldown_cap_seconds),
                        float(xsrf_cooldown_initial_seconds)
                        * (2 ** (consecutive_popup_xsrf - 1)),
                    )
                    logger.info(
                        "hh_ui_batch_xsrf_cooldown",
                        log_user_id=log_user_id,
                        vacancy_id=spec.autoparsed_vacancy_id,
                        consecutive=consecutive_popup_xsrf,
                        delay_s=delay,
                    )
                    time.sleep(delay)
                elif not _is_popup_xsrf_error_result(final):
                    consecutive_popup_xsrf = 0
        finally:
            dispose_sync_browser_context(context, browser)
    return results, None


def vacancy_url_from_hh_id(hh_vacancy_id: str) -> str:
    """Default public vacancy URL for a numeric id or full URL."""
    if hh_vacancy_id.startswith("http"):
        return hh_vacancy_id
    return f"https://hh.ru/vacancy/{hh_vacancy_id}"


def normalize_hh_vacancy_url(url: str | None, hh_vacancy_id: str) -> str:
    """Ensure a full https URL for Playwright (scraped rows may be relative or scheme-less)."""
    u = (url or "").strip()
    if u.startswith("https://"):
        return u
    if u.startswith("http://"):
        return "https://" + u[len("http://") :]
    if u.startswith("//"):
        return f"https:{u}"
    if u.startswith("/"):
        return f"https://hh.ru{u}"
    if u.startswith("hh.ru"):
        return f"https://{u}"
    return vacancy_url_from_hh_id(hh_vacancy_id)
