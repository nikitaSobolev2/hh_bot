"""HTTP fetch + HTML parse for hh.ru applicant negotiations (responses list)."""

from __future__ import annotations

import random
import re
import time
from typing import Any, Literal
from urllib.parse import urljoin, urlparse

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

_NEGOTIATIONS_PAGE_DELAY_FLOOR_S = 1.0
_NEGOTIATIONS_ITEM_SELECTOR = '[data-qa="negotiations-item"]'
_NEGOTIATIONS_ITEM_TITLE_SELECTOR = '[data-qa="negotiations-item-vacancy"]'
_NEGOTIATIONS_ITEM_COMPANY_SELECTOR = '[data-qa="negotiations-item-company"]'
_VACANCY_ID_RE = re.compile(r"/vacancy/(\d+)")
_VACANCY_QUERY_ID_RE = re.compile(r"[?&]vacancyId=(\d+)")
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


def _negotiations_page_delay_seconds(config: HhUiApplyConfig) -> float:
    lo = max(config.min_action_delay_ms / 1000.0, _NEGOTIATIONS_PAGE_DELAY_FLOOR_S)
    hi = max(config.max_action_delay_ms / 1000.0, lo)
    return random.uniform(lo, hi)


def _clean_text(text: str | None) -> str:
    return " ".join((text or "").replace("\xa0", " ").split())


def _append_unique_vacancy_ids(out: list[str], seen: set[str], text: str) -> None:
    for rx in (_VACANCY_QUERY_ID_RE, _VACANCY_ID_RE, _JSON_VACANCY_ID_RE, _JSON_VACANCY_ID_ALT_RE):
        for match in rx.finditer(text):
            vacancy_id = match.group(1)
            if vacancy_id in seen:
                continue
            seen.add(vacancy_id)
            out.append(vacancy_id)


def _ordered_negotiation_vacancy_ids_from_html(html: str, soup: BeautifulSoup | None = None) -> list[str]:
    soup = soup or BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    ordered: list[str] = []
    items = soup.select(_NEGOTIATIONS_ITEM_SELECTOR)
    for item in items:
        _append_unique_vacancy_ids(ordered, seen, str(item))
    scope = soup.select_one("main") or soup.select_one('[data-qa="negotiations-list"]')
    if scope is None:
        scope = soup
    _append_unique_vacancy_ids(ordered, seen, str(scope))
    for script in soup.find_all("script"):
        _append_unique_vacancy_ids(ordered, seen, script.string or script.get_text() or "")
    if not ordered:
        _append_unique_vacancy_ids(ordered, seen, html)
    return ordered


def _extract_negotiation_item_vacancy_id(item: BeautifulSoup) -> str | None:
    for attr in ("data-vacancy-id", "data-hh-vacancy-id", "data-vacancyId"):
        value = item.get(attr)
        if value and str(value).strip().isdigit():
            return str(value).strip()
    ordered = _ordered_negotiation_vacancy_ids_from_html(str(item))
    return ordered[0] if ordered else None


def _extract_negotiation_company_url(item: BeautifulSoup, final_url: str | None) -> str | None:
    base_url = final_url or "https://hh.ru"
    for link in item.find_all("a", href=True):
        href = str(link.get("href") or "")
        if "/employer/" not in href:
            continue
        return urljoin(base_url, href)
    return None


def _negotiation_card_dict(
    item: BeautifulSoup,
    vacancy_id: str | None,
    final_url: str | None,
) -> dict[str, str | None]:
    title_el = item.select_one(_NEGOTIATIONS_ITEM_TITLE_SELECTOR)
    company_el = item.select_one(_NEGOTIATIONS_ITEM_COMPANY_SELECTOR)
    title = _clean_text(title_el.get_text(" ", strip=True) if title_el else "")
    company_name = _clean_text(company_el.get_text(" ", strip=True) if company_el else "")
    return {
        "hh_vacancy_id": vacancy_id,
        "url": f"https://hh.ru/vacancy/{vacancy_id}" if vacancy_id else "",
        "title": title,
        "company_name": company_name or None,
        "company_url": _extract_negotiation_company_url(item, final_url),
    }


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


def parse_negotiation_vacancy_cards_from_html(
    html: str,
    final_url: str | None = None,
) -> tuple[dict[str, dict[str, str | None]], set[str]]:
    """Extract basic negotiations-card data keyed by HH vacancy id.

    Returns ``(cards_by_hh_id, all_detected_hh_ids)``. When a saved DOM card does not expose its
    own vacancy id, the parser falls back to ordered page-level ids only when counts line up.
    """
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select(_NEGOTIATIONS_ITEM_SELECTOR)
    ordered_page_ids = _ordered_negotiation_vacancy_ids_from_html(html, soup)
    cards = [
        _negotiation_card_dict(item, _extract_negotiation_item_vacancy_id(item), final_url)
        for item in items
    ]
    if cards and ordered_page_ids and len(ordered_page_ids) == len(cards):
        for card, vacancy_id in zip(cards, ordered_page_ids, strict=False):
            if card["hh_vacancy_id"]:
                continue
            card["hh_vacancy_id"] = vacancy_id
            card["url"] = f"https://hh.ru/vacancy/{vacancy_id}"

    cards_by_id: dict[str, dict[str, str | None]] = {}
    unresolved_cards = 0
    for card in cards:
        vacancy_id = card.get("hh_vacancy_id")
        if not vacancy_id:
            unresolved_cards += 1
            continue
        cards_by_id.setdefault(str(vacancy_id), card)
    if items:
        logger.info(
            "negotiations_parse_cards",
            cards=len(items),
            mapped_cards=len(cards_by_id),
            unresolved_cards=unresolved_cards,
        )
    return cards_by_id, set(ordered_page_ids)


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
        if page < max_pages:
            time.sleep(_negotiations_page_delay_seconds(config))
    return all_ids, None


def fetch_all_negotiation_vacancy_cards(
    storage_state: dict[str, Any],
    config: HhUiApplyConfig,
    *,
    max_pages: int = 100,
) -> tuple[dict[str, dict[str, str | None]], set[str], str | None]:
    """Fetch all negotiations pages and return basic card data plus all detected HH ids."""
    all_ids: set[str] = set()
    cards_by_id: dict[str, dict[str, str | None]] = {}
    for page in range(1, max_pages + 1):
        html, err, final_url = fetch_applicant_negotiations_html(storage_state, config, page=page)
        if err:
            return cards_by_id, all_ids, err
        if not html:
            break
        if final_url and url_suggests_login_page(final_url):
            return cards_by_id, all_ids, "login_redirect"
        try:
            path = urlparse(final_url or "").path.lower()
            if APPLICANT_NEGOTIATIONS_PATH.rstrip("/") not in path and page == 1:
                return cards_by_id, all_ids, "unexpected_url"
        except Exception:
            pass
        page_cards, page_ids = parse_negotiation_vacancy_cards_from_html(html, final_url)
        logger.info(
            "negotiations_parse_cards_page",
            page=page,
            page_cards=len(page_cards),
            page_unique_ids=len(page_ids),
            cumulative_unique=len(all_ids | page_ids),
        )
        if not page_ids:
            break
        new_only = page_ids - all_ids
        all_ids |= page_ids
        for vacancy_id, card in page_cards.items():
            cards_by_id.setdefault(vacancy_id, card)
        if not new_only and page > 1:
            break
        if page < max_pages:
            time.sleep(_negotiations_page_delay_seconds(config))
    return cards_by_id, all_ids, None
