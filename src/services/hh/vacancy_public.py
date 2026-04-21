"""Public HH API checks (no OAuth) for vacancy existence."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass

import httpx

from src.core.logging import get_logger
from src.services.hh_ui.config import HhUiApplyConfig
from src.services.hh_ui.runner import fetch_public_hh_api_json_via_browser

logger = get_logger(__name__)

HH_API_VACANCIES_BASE = "https://api.hh.ru/vacancies"
_HH_VACANCY_ID_RE = re.compile(r"^\d{1,20}$")
_DEFAULT_TIMEOUT = 15.0


@dataclass(frozen=True)
class HhVacancyPublicPreflight:
    """Result of GET /vacancies/{id} for routing before UI/API apply."""

    unavailable: bool
    """404, not_found payload, ``archived``/``hidden`` in JSON, or invalid id — skip + dislike."""
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
    if isinstance(test, dict) and test.get("required") is True:
        return True
    return False


def vacancy_public_json_is_archived_or_hidden(data: dict) -> bool:
    """True when vacancy JSON says archived or hidden (API fields on /vacancies/{id})."""
    if data.get("archived") is True:
        return True
    if data.get("hidden") is True:
        return True
    return False


def _headers() -> dict[str, str]:
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


def _vacancy_public_url(hh_vacancy_id: str) -> str:
    return f"{HH_API_VACANCIES_BASE}/{hh_vacancy_id}"


def _has_not_found_error(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    errs = payload.get("errors")
    if not isinstance(errs, list):
        return False
    for item in errs:
        if isinstance(item, dict) and item.get("type") == "not_found":
            return True
    return False


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


async def hh_vacancy_public_preflight(hh_vacancy_id: str) -> HhVacancyPublicPreflight:
    """GET /vacancies/{id}: unavailable vs employer test required (single request)."""
    vid = str(hh_vacancy_id or "").strip()
    if not _HH_VACANCY_ID_RE.match(vid):
        return HhVacancyPublicPreflight(unavailable=False, requires_employer_test=False)

    url = _vacancy_public_url(vid)
    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            resp = await client.get(url, headers=_headers())
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
    if try_playwright:
        cfg = HhUiApplyConfig.from_settings()
        data = await asyncio.to_thread(
            fetch_public_hh_api_json_via_browser,
            storage_state=None,
            config=cfg,
            api_url=url,
        )
        if isinstance(data, dict) and data and not _has_not_found_error(data):
            logger.info(
                "hh_vacancy_public_playwright_json_ok",
                hh_vacancy_id=vid,
                status=resp.status_code,
            )
            return _preflight_from_vacancy_json(data)

    # 429, 5xx, other — do not treat as unavailable or test (allow apply attempt)
    return HhVacancyPublicPreflight(unavailable=False, requires_employer_test=False)


async def hh_vacancy_public_is_unavailable(hh_vacancy_id: str) -> bool:
    """True if GET /vacancies/{id} indicates skip + dislike: 404, not_found, archived, or hidden."""
    p = await hh_vacancy_public_preflight(hh_vacancy_id)
    return p.unavailable
