"""HTTP fetch + HTML parse for hh.ru applicant resume list (no Playwright)."""

from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from src.services.hh_ui import selectors as sel
from src.services.hh_ui.config import HhUiApplyConfig
from src.services.hh_ui.outcomes import ApplyOutcome, ListResumesResult, ResumeOption

# Browser-like UA for hh.ru (avoid bare httpx default).
HH_APPLICANT_FETCH_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_RESUME_ID_RE = re.compile(r"/resume/([^/?#]+)")
# Only match real embeds — bundles often contain the substring "captcha" next to iframes (analytics, etc.).
_CAPTCHA_EMBED_RE = re.compile(
    r"<(?:iframe|script)[^>]+src=[\"'][^\"']*(?:smartcaptcha|captcha\.yandex|hcaptcha\.com|challenges\.cloudflare\.com)[^\"']*[\"']",
    re.IGNORECASE,
)


def httpx_cookies_from_storage_state(storage_state: dict[str, Any]) -> httpx.Cookies:
    """Map Playwright storage_state cookies to httpx Cookies (hh.ru only, skip expired)."""
    jar = httpx.Cookies()
    now = time.time()
    for c in storage_state.get("cookies") or []:
        if not isinstance(c, dict):
            continue
        domain = str(c.get("domain", ""))
        if "hh.ru" not in domain.lower():
            continue
        exp = c.get("expires")
        if isinstance(exp, (int, float)) and exp > 0 and exp < now:
            continue
        name = c.get("name")
        if not name:
            continue
        value = str(c.get("value") or "")
        path = str(c.get("path") or "/")
        jar.set(str(name), value, domain=domain, path=path)
    return jar


def fetch_applicant_resumes_html(
    storage_state: dict[str, Any],
    config: HhUiApplyConfig,
) -> tuple[str | None, str | None, str | None]:
    """GET /applicant/resumes with session cookies.

    Returns (html, error_detail, final_url_after_redirects).
    """
    cookies = httpx_cookies_from_storage_state(storage_state)
    timeout = max(config.navigation_timeout_ms / 1000.0, 5.0)
    headers = {
        "User-Agent": HH_APPLICANT_FETCH_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    }
    try:
        with httpx.Client(cookies=cookies, follow_redirects=True, timeout=timeout) as client:
            r = client.get(sel.APPLICANT_RESUMES_URL, headers=headers)
        if r.status_code != 200:
            return None, f"http_{r.status_code}", str(r.url)
        return r.text, None, str(r.url)
    except httpx.HTTPError as exc:
        return None, str(exc)[:200], None


def url_suggests_login_page(url: str) -> bool:
    """True if the HTTP client ended on a login/signup route (session expired)."""
    u = (url or "").lower()
    return "/account/login" in u or "/account/signup" in u


def url_is_applicant_resumes_document(url: str) -> bool:
    """True if the final URL is the applicant resume list (may be empty; still logged in)."""
    try:
        path = urlparse(url or "").path.lower().rstrip("/")
        return path.endswith("/applicant/resumes")
    except Exception:
        return False


def html_suggests_login(html: str) -> bool:
    """Heuristic: login page HTML.

    Authenticated /applicant/resumes often still contains footer links to account/login and
    data-qa=\"login\" in the chrome — do not treat those as session expired.
    """
    lower = html.lower()
    # Resume list (or empty-state) on applicant pages.
    if "resume-card-link" in lower or 'data-qa="resume-title"' in lower:
        return False
    if "account/login" in lower:
        return True
    if "вход в личный кабинет" in lower:
        return True
    if 'data-qa="login"' in html:
        return True
    return False


def html_suggests_captcha(html: str) -> bool:
    """True only when a captcha widget URL is embedded (iframe/script src).

    Do not use bare substrings like \"captcha\" or \"iframe\"+\"captcha\" — minified JS and
    unrelated strings cause false positives on normal logged-in pages.
    """
    low = html.lower()
    if "resume-card-link" in low or 'data-qa="resume-title"' in low:
        return False
    if _CAPTCHA_EMBED_RE.search(html):
        return True
    return False


def parse_applicant_resumes_from_html(html: str) -> ListResumesResult:
    """Parse resume cards from applicant/resumes HTML (Magritte layout)."""
    soup = BeautifulSoup(html, "html.parser")
    seen: dict[str, str] = {}
    for a in soup.find_all("a", attrs={"data-qa": True}):
        qa = str(a.get("data-qa") or "")
        if not qa.startswith("resume-card-link-"):
            continue
        href = str(a.get("href") or "")
        m = _RESUME_ID_RE.search(href)
        if not m:
            continue
        rid = m.group(1)
        if rid in seen:
            continue
        title_el = a.select_one('[data-qa="resume-title"] span[data-qa="cell-text-content"]')
        if not title_el:
            title_el = a.select_one('[data-qa="resume-title"]')
        title = (title_el.get_text() if title_el else "").strip()
        title = re.sub(r"\s+", " ", title) or rid
        seen[rid] = title[:200]

    resumes = [ResumeOption(id=k, title=v) for k, v in sorted(seen.items())]
    if not resumes:
        return ListResumesResult(
            resumes=[],
            outcome=ApplyOutcome.ERROR,
            detail="no_resume_links",
        )
    return ListResumesResult(resumes=resumes, outcome=ApplyOutcome.SUCCESS)
