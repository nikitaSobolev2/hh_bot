"""HTTP fetch + HTML parse for hh.ru applicant negotiations (responses list)."""

from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from src.services.hh_ui.applicant_http import (
    HH_APPLICANT_FETCH_USER_AGENT,
    httpx_cookies_from_storage_state,
    url_suggests_login_page,
)
from src.core.logging import get_logger
from src.services.hh_ui.config import HhUiApplyConfig
from src.services.hh_ui.selectors import APPLICANT_NEGOTIATIONS_PATH

logger = get_logger(__name__)

NegotiationsSessionAvailability = Literal["ok", "login", "unexpected_url", "error"]

_VACANCY_ID_RE = re.compile(r"/vacancy/(\d+)")
# Embedded JSON in Magritte / state blobs (6+ digits — HH vacancy ids are long).
_JSON_VACANCY_ID_RE = re.compile(r'"vacancyId"\s*:\s*"?(\d{6,})"?')
_JSON_VACANCY_ID_ALT_RE = re.compile(r'"vacancy_id"\s*:\s*"?(\d{6,})"?')


def _negotiations_url(base: str, page: int) -> str:
    b = base.rstrip("/")
    if page <= 1:
        return f"{b}{APPLICANT_NEGOTIATIONS_PATH}"
    return f"{b}{APPLICANT_NEGOTIATIONS_PATH}?page={page}"


def _negotiations_base_url(storage_state: dict[str, Any]) -> str:
    """Prefer regional host from cookies (e.g. izhevsk.hh.ru), else hh.ru."""
    for c in storage_state.get("cookies") or []:
        if not isinstance(c, dict):
            continue
        domain = str(c.get("domain", "")).lower()
        if "hh.ru" not in domain:
            continue
        d = domain.lstrip(".")
        if d.endswith("hh.ru") and d != "hh.ru":
            return f"https://{d}"
    return "https://hh.ru"


def fetch_applicant_negotiations_html(
    storage_state: dict[str, Any],
    config: HhUiApplyConfig,
    *,
    page: int = 1,
) -> tuple[str | None, str | None, str | None]:
    """GET applicant/negotiations with session cookies.

    Returns (html, error_detail, final_url_after_redirects).
    """
    base = _negotiations_base_url(storage_state)
    url = _negotiations_url(base, page)
    cookies = httpx_cookies_from_storage_state(storage_state)
    timeout = max(config.navigation_timeout_ms / 1000.0, 5.0)
    headers = {
        "User-Agent": HH_APPLICANT_FETCH_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    }
    try:
        with httpx.Client(cookies=cookies, follow_redirects=True, timeout=timeout) as client:
            r = client.get(url, headers=headers)
        if r.status_code != 200:
            return None, f"http_{r.status_code}", str(r.url)
        return r.text, None, str(r.url)
    except httpx.HTTPError as exc:
        return None, str(exc)[:200], None


def classify_negotiations_session_fetch(
    html: str | None,
    err: str | None,
    final_url: str | None,
) -> tuple[NegotiationsSessionAvailability, str | None]:
    """Classify first-page GET /applicant/negotiations result (same rules as negotiations sync).

    *err* is set when HTTP status was not 200 or the client raised (see
    :func:`fetch_applicant_negotiations_html`).
    """
    if err:
        return "error", err
    if not html:
        return "error", "empty_response"
    if final_url and url_suggests_login_page(final_url):
        return "login", None
    try:
        path = urlparse(final_url or "").path.lower()
        if APPLICANT_NEGOTIATIONS_PATH.rstrip("/") not in path:
            return "unexpected_url", None
    except Exception:
        return "unexpected_url", "url_parse"
    return "ok", None


def check_negotiations_browser_session_available(
    storage_state: dict[str, Any],
    config: HhUiApplyConfig,
) -> tuple[NegotiationsSessionAvailability, str | None]:
    """GET negotiations page once and classify session liveness for UI checks."""
    html, err, final_url = fetch_applicant_negotiations_html(storage_state, config, page=1)
    return classify_negotiations_session_fetch(html, err, final_url)


def parse_negotiation_vacancy_ids_from_html(html: str) -> set[str]:
    """Extract numeric vacancy ids from negotiations list HTML.

    HH «Все» can count negotiation *threads* (incl. duplicates / non-vacancy rows);
    we dedupe by vacancy id. Rows may expose id in ``data-*``, links, or embedded JSON.
    """
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    items = soup.select('[data-qa="negotiations-item"]')
    roots = items if items else [soup]
    for root in roots:
        for a in root.find_all("a", href=True):
            href = str(a.get("href") or "")
            m = _VACANCY_ID_RE.search(href)
            if m:
                seen.add(m.group(1))
    for item in items:
        for attr in ("data-vacancy-id", "data-hh-vacancy-id", "data-vacancyId"):
            v = item.get(attr)
            if v and str(v).strip().isdigit():
                seen.add(str(v).strip())
    # All /vacancy/<id> in main list area (some rows hide the link outside <a>).
    scope = soup.select_one("main") or soup.select_one('[data-qa="negotiations-list"]')
    if scope is None:
        scope = soup
    scope_html = str(scope)
    for m in _VACANCY_ID_RE.finditer(scope_html):
        seen.add(m.group(1))
    # Embedded JSON (SSR may be partial; state blob can list more ids).
    for rx in (_JSON_VACANCY_ID_RE, _JSON_VACANCY_ID_ALT_RE):
        for m in rx.finditer(scope_html):
            seen.add(m.group(1))
    for script in soup.find_all("script"):
        chunk = script.string or script.get_text() or ""
        for rx in (_JSON_VACANCY_ID_RE, _JSON_VACANCY_ID_ALT_RE):
            for m in rx.finditer(chunk):
                seen.add(m.group(1))
    if not seen:
        for m in _VACANCY_ID_RE.finditer(html):
            seen.add(m.group(1))
    return seen


def fetch_all_negotiation_vacancy_ids(
    storage_state: dict[str, Any],
    config: HhUiApplyConfig,
    *,
    max_pages: int = 100,
) -> tuple[set[str], str | None]:
    """Fetch all pages until no new ids or empty page. Returns (ids, error)."""
    all_ids: set[str] = set()
    for page in range(1, max_pages + 1):
        html, err, final_url = fetch_applicant_negotiations_html(storage_state, config, page=page)
        if err:
            return all_ids, err
        if not html:
            break
        if final_url and url_suggests_login_page(final_url):
            return all_ids, "login_redirect"
        try:
            path = urlparse(final_url or "").path.lower()
            if APPLICANT_NEGOTIATIONS_PATH.rstrip("/") not in path and page == 1:
                return all_ids, "unexpected_url"
        except Exception:
            pass
        page_ids = parse_negotiation_vacancy_ids_from_html(html)
        logger.info(
            "negotiations_parse_page",
            page=page,
            page_unique_ids=len(page_ids),
            cumulative_unique=len(all_ids | page_ids),
        )
        if not page_ids:
            break
        new_only = page_ids - all_ids
        if not new_only and page > 1:
            break
        all_ids |= page_ids
    return all_ids, None
