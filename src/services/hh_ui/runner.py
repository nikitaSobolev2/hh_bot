"""Sync Playwright runners for HH.ru resume list and vacancy apply."""

from __future__ import annotations

import random
import re
import time
from typing import Any

from playwright.sync_api import Locator
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from src.services.hh_ui import selectors as sel
from src.services.hh_ui.config import HhUiApplyConfig
from src.services.hh_ui.outcomes import ApplyOutcome, ApplyResult, ListResumesResult, ResumeOption

_RESUME_ID_RE = re.compile(r"/resume/([^/?#]+)")


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


def _detect_captcha(page: Any) -> bool:
    for hint in sel.CAPTCHA_HINTS:
        try:
            if page.locator(hint).count() > 0:
                return True
        except Exception:
            continue
    content = ""
    try:
        content = page.content()
    except Exception:
        return False
    return "smartcaptcha" in content.lower() or "hcaptcha" in content.lower()


def _detect_login(page: Any) -> bool:
    for hint in sel.LOGIN_FORM:
        try:
            if page.locator(hint).count() > 0:
                return True
        except Exception:
            continue
    u = page.url
    return "login" in u or "account/login" in u


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


def _wait_response_modal_visible(page: Any, timeout_ms: int) -> None:
    page.locator(sel.RESPONSE_MODAL_CONTENT).first.wait_for(state="visible", timeout=timeout_ms)
    try:
        page.get_by_text(sel.RESPONSE_MODAL_TITLE_TEXT, exact=False).first.wait_for(
            state="visible",
            timeout=min(5000, timeout_ms),
        )
    except PlaywrightTimeoutError:
        pass


def _collect_resumes_from_modal(page: Any) -> list[ResumeOption]:
    """Parse radio name=resumeId + data-qa=resume-title inside the respond bottom sheet."""
    out: list[ResumeOption] = []
    for radio in page.locator(sel.RESUME_RADIO).all():
        try:
            rid = (radio.get_attribute("value") or "").strip()
            if not rid:
                continue
            label = page.locator(f'label:has(input[name="resumeId"][value="{rid}"])').first
            try:
                title_loc = label.locator(sel.RESUME_TITLE_IN_MODAL).first
                title_loc.wait_for(state="visible", timeout=3000)
                title = (title_loc.inner_text() or "").strip() or rid
            except Exception:
                title = rid
            out.append(ResumeOption(id=rid, title=title[:200]))
        except Exception:
            continue
    return out


def _close_response_modal(page: Any) -> None:
    btn = page.locator(sel.RESPONSE_MODAL_CLOSE).first
    try:
        if btn.is_visible():
            btn.click()
            page.wait_for_timeout(400)
    except Exception:
        pass


def _list_resumes_from_applicant_page(page: Any) -> ListResumesResult:
    seen: dict[str, str] = {}
    for link in page.locator(sel.RESUME_LIST_LINK).all():
        try:
            href = link.get_attribute("href") or ""
        except Exception:
            continue
        m = _RESUME_ID_RE.search(href)
        if not m:
            continue
        rid = m.group(1)
        if rid in seen:
            continue
        try:
            title = (link.inner_text() or "").strip() or rid
        except Exception:
            title = rid
        seen[rid] = title[:200]

    resumes = [ResumeOption(id=k, title=v) for k, v in sorted(seen.items())]
    if not resumes:
        return ListResumesResult(
            resumes=[],
            outcome=ApplyOutcome.ERROR,
            detail="no_resume_links",
        )
    return ListResumesResult(resumes=resumes, outcome=ApplyOutcome.SUCCESS)


def list_resumes_ui(
    *,
    storage_state: dict[str, Any],
    config: HhUiApplyConfig,
    vacancy_url: str | None = None,
) -> ListResumesResult:
    """Load resume list for Telegram pick: prefer Magritte modal on vacancy page, else /applicant/resumes."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.headless)
        try:
            context = browser.new_context(storage_state=storage_state)
            page = context.new_page()
            timeout = config.action_timeout_ms

            if vacancy_url and vacancy_url.startswith("https://"):
                try:
                    page.goto(
                        vacancy_url,
                        wait_until="domcontentloaded",
                        timeout=config.navigation_timeout_ms,
                    )
                    _jitter(config)
                    if _detect_login(page):
                        return ListResumesResult(
                            resumes=[],
                            outcome=ApplyOutcome.SESSION_EXPIRED,
                            detail="login_form",
                        )
                    if _detect_captcha(page):
                        return ListResumesResult(
                            resumes=[],
                            outcome=ApplyOutcome.CAPTCHA,
                            detail="captcha",
                        )
                    if _click_first(
                        page,
                        sel.VACANCY_APPLY_BUTTON,
                        min(2000, timeout),
                    ):
                        _jitter(config)
                        page.wait_for_timeout(400)
                        _wait_response_modal_visible(page, timeout)
                        modal_resumes = _collect_resumes_from_modal(page)
                        _close_response_modal(page)
                        if modal_resumes:
                            return ListResumesResult(
                                resumes=modal_resumes,
                                outcome=ApplyOutcome.SUCCESS,
                            )
                except Exception:
                    pass

            page.goto(
                sel.APPLICANT_RESUMES_URL,
                wait_until="domcontentloaded",
                timeout=config.navigation_timeout_ms,
            )
            _jitter(config)
            if _detect_login(page):
                return ListResumesResult(
                    resumes=[],
                    outcome=ApplyOutcome.SESSION_EXPIRED,
                    detail="login_form",
                )
            if _detect_captcha(page):
                return ListResumesResult(
                    resumes=[],
                    outcome=ApplyOutcome.CAPTCHA,
                    detail="captcha",
                )
            return _list_resumes_from_applicant_page(page)
        finally:
            browser.close()


def apply_to_vacancy_ui(
    *,
    storage_state: dict[str, Any],
    vacancy_url: str,
    resume_hh_id: str,
    config: HhUiApplyConfig,
) -> ApplyResult:
    """Open vacancy page and submit respond via UI."""
    if not vacancy_url.startswith("https://"):
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

            if _detect_login(page):
                return ApplyResult(
                    outcome=ApplyOutcome.SESSION_EXPIRED,
                    detail="login_form",
                )
            if _detect_captcha(page):
                shot = _maybe_screenshot(page, config)
                return ApplyResult(
                    outcome=ApplyOutcome.CAPTCHA,
                    detail="captcha",
                    screenshot_bytes=shot,
                )

            if _detect_already_applied(page):
                return ApplyResult(outcome=ApplyOutcome.ALREADY_RESPONDED)

            if not _click_first(
                page,
                sel.VACANCY_APPLY_BUTTON,
                min(2000, config.action_timeout_ms),
            ):
                shot = _maybe_screenshot(page, config)
                return ApplyResult(
                    outcome=ApplyOutcome.NO_APPLY_BUTTON,
                    detail="no_apply_button",
                    screenshot_bytes=shot,
                )

            _jitter(config)
            page.wait_for_timeout(500)

            if _detect_already_applied(page):
                return ApplyResult(outcome=ApplyOutcome.ALREADY_RESPONDED)

            if _detect_employer_questions(page):
                return ApplyResult(
                    outcome=ApplyOutcome.EMPLOYER_QUESTIONS,
                    detail="employer_questions",
                )

            if _detect_captcha(page):
                shot = _maybe_screenshot(page, config)
                return ApplyResult(
                    outcome=ApplyOutcome.CAPTCHA,
                    detail="captcha_after_click",
                    screenshot_bytes=shot,
                )

            selected = False
            modal_visible = False
            try:
                _wait_response_modal_visible(page, config.action_timeout_ms)
                modal_visible = True
            except PlaywrightTimeoutError:
                pass
            if modal_visible:
                try:
                    radio = page.locator(f'input[name="resumeId"][value="{resume_hh_id}"]').first
                    radio.wait_for(state="visible", timeout=config.action_timeout_ms)
                    radio.check()
                    selected = True
                except Exception:
                    try:
                        lbl = page.locator(
                            f'label:has(input[name="resumeId"][value="{resume_hh_id}"])'
                        ).first
                        lbl.wait_for(state="visible", timeout=config.action_timeout_ms)
                        lbl.click()
                        selected = True
                    except Exception:
                        pass

            if not selected:
                for s in sel.RESUME_SELECT:
                    loc = page.locator(s).first
                    try:
                        loc.wait_for(state="visible", timeout=config.action_timeout_ms)
                        loc.select_option(value=resume_hh_id)
                        selected = True
                        break
                    except Exception:
                        continue

            if not selected:
                alt = page.locator(f'a[href*="/resume/{resume_hh_id}"]').first
                try:
                    alt.wait_for(state="visible", timeout=config.action_timeout_ms)
                    alt.click()
                    selected = True
                except Exception:
                    pass

            if not selected:
                shot = _maybe_screenshot(page, config)
                return ApplyResult(
                    outcome=ApplyOutcome.ERROR,
                    detail="resume_not_selectable",
                    screenshot_bytes=shot,
                )

            _jitter(config)

            modal_root = page.locator(sel.RESPONSE_MODAL_CONTENT).first
            submitted = False
            try:
                if modal_root.is_visible():
                    submitted = _click_first_in_root(
                        modal_root,
                        sel.RESUME_SUBMIT,
                        config.action_timeout_ms,
                    )
            except Exception:
                pass
            if not submitted:
                submitted = _click_first(
                    page,
                    sel.RESUME_SUBMIT,
                    config.action_timeout_ms,
                )
            if not submitted:
                shot = _maybe_screenshot(page, config)
                return ApplyResult(
                    outcome=ApplyOutcome.ERROR,
                    detail="submit_not_found",
                    screenshot_bytes=shot,
                )

            _jitter(config)
            page.wait_for_timeout(500)

            if _detect_already_applied(page):
                return ApplyResult(outcome=ApplyOutcome.ALREADY_RESPONDED)

            if _detect_employer_questions(page):
                return ApplyResult(
                    outcome=ApplyOutcome.EMPLOYER_QUESTIONS,
                    detail="employer_questions_after_submit",
                )

            return ApplyResult(outcome=ApplyOutcome.SUCCESS)
        except PlaywrightTimeoutError as exc:
            return ApplyResult(
                outcome=ApplyOutcome.ERROR,
                detail=f"timeout:{exc}",
            )
        except Exception as exc:
            return ApplyResult(
                outcome=ApplyOutcome.ERROR,
                detail=str(exc)[:500],
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
