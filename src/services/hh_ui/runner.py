"""Sync Playwright runners for HH.ru resume list and vacancy apply."""

from __future__ import annotations

import random
import time
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
from src.services.hh_ui.vacancy_response_popup import try_apply_via_popup
from src.services.hh_ui.outcomes import ApplyOutcome, ApplyResult, ListResumesResult, ResumeOption

logger = get_logger(__name__)


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


def _screenshot_page_captcha(page: Any) -> bytes | None:
    """Always capture the page when captcha is shown (not gated by screenshot_on_error)."""
    try:
        return page.screenshot(type="png", full_page=True)
    except Exception:
        return None


def _screenshot_url_with_storage(
    storage_state: dict[str, Any],
    config: HhUiApplyConfig,
    url: str,
) -> bytes | None:
    """Open Chromium with the same Playwright storage_state and screenshot (e.g. HTTP-detected captcha)."""
    with sync_playwright() as p:
        browser = None
        try:
            browser = p.chromium.launch(headless=config.headless)
            context = browser.new_context(storage_state=storage_state)
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
            if browser is not None:
                browser.close()


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
        browser = p.chromium.launch(headless=config.headless)
        try:
            context = browser.new_context(storage_state=storage_state)
            page = context.new_page()
            page.goto(
                vacancy_url,
                wait_until="domcontentloaded",
                timeout=config.navigation_timeout_ms,
            )
            _jitter(config)
            logger.info(
                "apply_to_vacancy_ui_step",
                log_user_id=log_user_id,
                step="after_goto",
                vacancy_url_safe=safe_v,
                resume_ref=resume_ref,
            )

            if _detect_login(page):
                logger.info(
                    "apply_to_vacancy_ui_done",
                    log_user_id=log_user_id,
                    vacancy_url_safe=safe_v,
                    resume_ref=resume_ref,
                    outcome=ApplyOutcome.SESSION_EXPIRED.value,
                    detail="login_form",
                )
                return ApplyResult(
                    outcome=ApplyOutcome.SESSION_EXPIRED,
                    detail="login_form",
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
                return ApplyResult(
                    outcome=ApplyOutcome.CAPTCHA,
                    detail="captcha",
                    screenshot_bytes=shot,
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
                return ApplyResult(outcome=ApplyOutcome.ALREADY_RESPONDED)

            if config.use_popup_api:
                popup_result = try_apply_via_popup(
                    page,
                    vacancy_url,
                    resume_hh_id,
                    log_user_id=log_user_id,
                )
                if popup_result is not None:
                    logger.info(
                        "apply_to_vacancy_ui_done",
                        log_user_id=log_user_id,
                        step="popup_api",
                        vacancy_url_safe=safe_v,
                        resume_ref=resume_ref,
                        outcome=popup_result.outcome.value,
                        detail=(popup_result.detail or "")[:200] if popup_result.detail else None,
                    )
                    return popup_result

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
                return ApplyResult(
                    outcome=ApplyOutcome.NO_APPLY_BUTTON,
                    detail="no_apply_button",
                    screenshot_bytes=shot,
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
                return ApplyResult(outcome=ApplyOutcome.ALREADY_RESPONDED)

            if _detect_employer_questions(page):
                logger.info(
                    "apply_to_vacancy_ui_done",
                    log_user_id=log_user_id,
                    vacancy_url_safe=safe_v,
                    resume_ref=resume_ref,
                    outcome=ApplyOutcome.EMPLOYER_QUESTIONS.value,
                    detail="employer_questions",
                )
                return ApplyResult(
                    outcome=ApplyOutcome.EMPLOYER_QUESTIONS,
                    detail="employer_questions",
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
                return ApplyResult(
                    outcome=ApplyOutcome.CAPTCHA,
                    detail="captcha_after_click",
                    screenshot_bytes=shot,
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
            select_mode = "none"
            # Always try resume selection even if sheet wait failed (layout may still expose radios).
            try:
                radio = page.locator(f'input[name="resumeId"][value="{resume_hh_id}"]').first
                radio.wait_for(state="attached", timeout=config.action_timeout_ms)
                radio.check(force=True)
                selected = True
                select_mode = "radio"
            except Exception:
                try:
                    lbl = page.locator(
                        f'label:has(input[name="resumeId"][value="{resume_hh_id}"])'
                    ).first
                    lbl.wait_for(state="visible", timeout=config.action_timeout_ms)
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
                    card.click()
                    selected = True
                    select_mode = "resume_card"
                except Exception:
                    pass

            if not selected:
                alt = page.locator(f'a[href*="/resume/{resume_hh_id}"]').first
                try:
                    alt.wait_for(state="visible", timeout=config.action_timeout_ms)
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
                return ApplyResult(
                    outcome=ApplyOutcome.ERROR,
                    detail="resume_not_selectable",
                    screenshot_bytes=shot,
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
                return ApplyResult(
                    outcome=ApplyOutcome.ERROR,
                    detail="submit_not_found",
                    screenshot_bytes=shot,
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
                return ApplyResult(outcome=ApplyOutcome.ALREADY_RESPONDED)

            if _detect_employer_questions(page):
                logger.info(
                    "apply_to_vacancy_ui_done",
                    log_user_id=log_user_id,
                    vacancy_url_safe=safe_v,
                    resume_ref=resume_ref,
                    outcome=ApplyOutcome.EMPLOYER_QUESTIONS.value,
                    detail="employer_questions_after_submit",
                )
                return ApplyResult(
                    outcome=ApplyOutcome.EMPLOYER_QUESTIONS,
                    detail="employer_questions_after_submit",
                )

            logger.info(
                "apply_to_vacancy_ui_done",
                log_user_id=log_user_id,
                vacancy_url_safe=safe_v,
                resume_ref=resume_ref,
                outcome=ApplyOutcome.SUCCESS.value,
                detail=None,
            )
            return ApplyResult(outcome=ApplyOutcome.SUCCESS)
        except PlaywrightTimeoutError as exc:
            logger.info(
                "apply_to_vacancy_ui_done",
                log_user_id=log_user_id,
                vacancy_url_safe=safe_v,
                resume_ref=resume_ref,
                outcome=ApplyOutcome.ERROR.value,
                detail=f"timeout:{exc}"[:200],
            )
            return ApplyResult(
                outcome=ApplyOutcome.ERROR,
                detail=f"timeout:{exc}",
            )
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
            return ApplyResult(
                outcome=ApplyOutcome.ERROR,
                detail=d,
            )
        finally:
            browser.close()


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
