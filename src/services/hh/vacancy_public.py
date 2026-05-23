"""Public HH vacancy checks (no OAuth) for routing before apply."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

from src.config import settings
from src.core.logging import get_logger
from src.services.hh_ui.applicant_http import url_suggests_login_page
from src.services.hh_ui.config import HhUiApplyConfig
from src.services.hh_ui.runner import (
    fetch_public_hh_api_json_via_browser,
    render_vacancy_detail_page_with_storage,
    vacancy_url_from_hh_id,
)

logger = get_logger(__name__)

HH_API_VACANCIES_BASE = "https://api.hh.ru/vacancies"
_HH_VACANCY_ID_RE = re.compile(r"^\d{1,20}$")
_DEFAULT_TIMEOUT = 15.0
_VACANCY_DESCRIPTION_SELECTOR = '[data-qa="vacancy-description"]'
_EMBEDDED_ARCHIVED_RE = re.compile(r'"archived"\s*:\s*true', re.IGNORECASE)
_EMBEDDED_HIDDEN_RE = re.compile(r'"hidden"\s*:\s*true', re.IGNORECASE)
_EMBEDDED_HAS_TEST_RE = re.compile(r'"(?:has_test|hasTests)"\s*:\s*true', re.IGNORECASE)
_EMBEDDED_TEST_REQUIRED_RE = re.compile(
    r'"test"\s*:\s*\{[^}]*"required"\s*:\s*true',
    re.IGNORECASE,
)


@dataclass(frozen=True)
class HhVacancyPublicPreflight:
    """Result of vacancy availability probe for routing before UI/API apply."""

    unavailable: bool
    """404, not_found payload, ``archived``/``hidden``, or invalid id — skip + dislike."""
    requires_employer_test: bool
    """Employer test on hh.ru; skip automated apply and mark needs_employer_questions."""

    @property
    def ok_to_auto_apply(self) -> bool:
        return not self.unavailable and not self.requires_employer_test


def vacancy_public_json_requires_employer_test(data: dict) -> bool:
    """True when public vacancy JSON indicates an employer test (API: has_test / test.required)."""
    if data.get("has_test") is True:
        return True
    test = data.get("test")
    return isinstance(test, dict) and test.get("required") is True


def vacancy_public_json_is_archived_or_hidden(data: dict) -> bool:
    """True when vacancy JSON says archived or hidden (API fields on /vacancies/{id})."""
    return data.get("archived") is True or data.get("hidden") is True


def _headers_api() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }


def _headers_html() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }


def _vacancy_public_api_url(hh_vacancy_id: str) -> str:
    return f"{HH_API_VACANCIES_BASE}/{hh_vacancy_id}"


def _has_not_found_error(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    errs = payload.get("errors")
    if not isinstance(errs, list):
        return False
    return any(
        isinstance(item, dict) and item.get("type") == "not_found" for item in errs
    )


def _body_suggests_public_api_block(body: str) -> bool:
    if not body:
        return False
    low = body.lower()
    if "captcha" in low:
        return True
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return False
    errs = data.get("errors") if isinstance(data, dict) else None
    if not isinstance(errs, list):
        return False
    for item in errs:
        if not isinstance(item, dict):
            continue
        if item.get("type") in ("forbidden", "captcha_required"):
            return True
    return False


def _preflight_from_vacancy_json(data: dict) -> HhVacancyPublicPreflight:
    if _has_not_found_error(data):
        return HhVacancyPublicPreflight(unavailable=True, requires_employer_test=False)
    if vacancy_public_json_is_archived_or_hidden(data):
        return HhVacancyPublicPreflight(unavailable=True, requires_employer_test=False)
    needs_test = vacancy_public_json_requires_employer_test(data)
    return HhVacancyPublicPreflight(unavailable=False, requires_employer_test=needs_test)


def _html_suggests_not_found(soup: BeautifulSoup) -> bool:
    title = (soup.find("title").get_text(strip=True) if soup.find("title") else "").lower()
    if "404" in title or "не найден" in title or "not found" in title:
        return True
    body_text = soup.get_text(" ", strip=True).lower()
    return "такой вакансии нет" in body_text or "vacancy not found" in body_text


def _html_suggests_employer_test(html: str) -> bool:
    if _EMBEDDED_HAS_TEST_RE.search(html):
        return True
    return bool(_EMBEDDED_TEST_REQUIRED_RE.search(html))


def _html_suggests_archived_or_hidden(html: str) -> bool:
    if _EMBEDDED_ARCHIVED_RE.search(html):
        return True
    return bool(_EMBEDDED_HIDDEN_RE.search(html))


def _preflight_from_vacancy_html(
    html: str | None,
    *,
    final_url: str | None,
) -> HhVacancyPublicPreflight:
    if not html:
        return HhVacancyPublicPreflight(unavailable=False, requires_employer_test=False)
    if final_url and url_suggests_login_page(final_url):
        return HhVacancyPublicPreflight(unavailable=False, requires_employer_test=False)

    soup = BeautifulSoup(html, "html.parser")
    has_description = soup.select_one(_VACANCY_DESCRIPTION_SELECTOR) is not None

    if _html_suggests_not_found(soup):
        return HhVacancyPublicPreflight(unavailable=True, requires_employer_test=False)

    if _html_suggests_archived_or_hidden(html):
        return HhVacancyPublicPreflight(unavailable=True, requires_employer_test=False)

    if not has_description:
        return HhVacancyPublicPreflight(unavailable=True, requires_employer_test=False)

    needs_test = _html_suggests_employer_test(html)
    return HhVacancyPublicPreflight(unavailable=False, requires_employer_test=needs_test)


async def _hh_vacancy_api_preflight(
    vid: str,
    *,
    allow_playwright_fallback: bool = True,
) -> HhVacancyPublicPreflight:
    url = _vacancy_public_api_url(vid)
    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, headers=_headers_api())
    except httpx.HTTPError as exc:
        logger.warning(
            "hh_vacancy_public_request_failed",
            hh_vacancy_id=vid,
            error=str(exc)[:300],
        )
        return HhVacancyPublicPreflight(unavailable=False, requires_employer_test=False)
    except Exception as exc:
        logger.warning(
            "hh_vacancy_public_request_failed",
            hh_vacancy_id=vid,
            error=str(exc)[:300],
        )
        return HhVacancyPublicPreflight(unavailable=False, requires_employer_test=False)

    if resp.status_code == 404:
        return HhVacancyPublicPreflight(unavailable=True, requires_employer_test=False)

    if 200 <= resp.status_code < 300:
        try:
            data = resp.json()
        except Exception:
            return HhVacancyPublicPreflight(unavailable=False, requires_employer_test=False)
        if not isinstance(data, dict):
            return HhVacancyPublicPreflight(unavailable=False, requires_employer_test=False)
        return _preflight_from_vacancy_json(data)

    body_preview = (resp.text or "")[:800]
    try_playwright = resp.status_code in (403, 429) or _body_suggests_public_api_block(body_preview)
    if try_playwright and allow_playwright_fallback:
        cfg = HhUiApplyConfig.from_settings()
        data = await asyncio.to_thread(
            fetch_public_hh_api_json_via_browser,
            storage_state=None,
            config=cfg,
            api_url=url,
        )
        if (
            isinstance(data, dict)
            and data.get("id")
            and not _has_not_found_error(data)
            and not _body_suggests_public_api_block(json.dumps(data))
        ):
            logger.info(
                "hh_vacancy_public_playwright_json_ok",
                hh_vacancy_id=vid,
                status=resp.status_code,
            )
            return _preflight_from_vacancy_json(data)

    if try_playwright and not allow_playwright_fallback:
        logger.info(
            "hh_vacancy_public_playwright_skipped",
            hh_vacancy_id=vid,
            status=resp.status_code,
        )

    return HhVacancyPublicPreflight(unavailable=False, requires_employer_test=False)


async def _hh_vacancy_web_preflight(
    vid: str,
    *,
    allow_playwright_fallback: bool = True,
) -> HhVacancyPublicPreflight:
    url = vacancy_url_from_hh_id(vid)
    html: str | None = None
    final_url: str | None = None
    needs_playwright = False

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, headers=_headers_html())
            final_url = str(resp.url)
            if resp.status_code == 404:
                return HhVacancyPublicPreflight(unavailable=True, requires_employer_test=False)
            if 200 <= resp.status_code < 300:
                html = resp.text
            elif resp.status_code in (403, 429):
                needs_playwright = True
    except httpx.HTTPError as exc:
        logger.warning(
            "hh_vacancy_web_preflight_request_failed",
            hh_vacancy_id=vid,
            error=str(exc)[:300],
        )
        needs_playwright = True
    except Exception as exc:
        logger.warning(
            "hh_vacancy_web_preflight_request_failed",
            hh_vacancy_id=vid,
            error=str(exc)[:300],
        )
        needs_playwright = True

    if html is None or needs_playwright:
        if not allow_playwright_fallback:
            logger.info(
                "hh_vacancy_web_preflight_playwright_skipped",
                hh_vacancy_id=vid,
                needs_playwright=needs_playwright,
            )
            return HhVacancyPublicPreflight(unavailable=False, requires_employer_test=False)
        cfg = HhUiApplyConfig.from_settings()
        rendered = await asyncio.to_thread(
            render_vacancy_detail_page_with_storage,
            storage_state=None,
            config=cfg,
            url=url,
        )
        html = rendered.html
        final_url = rendered.final_url or final_url
        if html:
            logger.info(
                "hh_vacancy_web_preflight_playwright_ok",
                hh_vacancy_id=vid,
                final_url=final_url,
            )

    return _preflight_from_vacancy_html(html, final_url=final_url)


async def hh_vacancy_public_preflight(
    hh_vacancy_id: str,
    *,
    allow_playwright_fallback: bool = True,
) -> HhVacancyPublicPreflight:
    """Probe vacancy availability before apply (public API or HTML per admin setting)."""
    vid = str(hh_vacancy_id or "").strip()
    if not _HH_VACANCY_ID_RE.match(vid):
        return HhVacancyPublicPreflight(unavailable=False, requires_employer_test=False)

    if settings.hh_api_vacancy_parsing_enabled:
        return await _hh_vacancy_api_preflight(
            vid,
            allow_playwright_fallback=allow_playwright_fallback,
        )
    return await _hh_vacancy_web_preflight(
        vid,
        allow_playwright_fallback=allow_playwright_fallback,
    )


async def hh_vacancy_public_is_unavailable(hh_vacancy_id: str) -> bool:
    """True if vacancy probe indicates skip + dislike: 404, not_found, archived, or hidden."""
    p = await hh_vacancy_public_preflight(hh_vacancy_id)
    return p.unavailable
