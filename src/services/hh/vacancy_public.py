"""Public HH API checks (no OAuth) for vacancy existence."""

from __future__ import annotations

import re

import httpx

from src.core.logging import get_logger

logger = get_logger(__name__)

HH_API_VACANCIES_BASE = "https://api.hh.ru/vacancies"
_HH_VACANCY_ID_RE = re.compile(r"^\d{1,20}$")
_DEFAULT_TIMEOUT = 15.0


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


async def hh_vacancy_public_is_unavailable(hh_vacancy_id: str) -> bool:
    """True if GET /vacancies/{id} indicates the vacancy is gone (404 or not_found)."""
    vid = str(hh_vacancy_id or "").strip()
    if not _HH_VACANCY_ID_RE.match(vid):
        return False

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
        return False
    except Exception as exc:
        logger.warning(
            "hh_vacancy_public_request_failed",
            hh_vacancy_id=vid,
            error=str(exc)[:300],
        )
        return False

    if resp.status_code == 404:
        return True

    if 200 <= resp.status_code < 300:
        try:
            data = resp.json()
        except Exception:
            return False
        if _has_not_found_error(data):
            return True
        return False

    # 429, 5xx, other — do not treat as unavailable
    return False
