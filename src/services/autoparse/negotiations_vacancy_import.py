"""Fetch HH vacancy JSON (public API) and build vac dicts for AutoparsedVacancy rows."""

from __future__ import annotations

import asyncio

import httpx

from src.config import settings
from src.core.logging import get_logger
from src.schemas.vacancy import build_vacancy_api_context
from src.services.hh_ui.applicant_http import httpx_cookies_from_storage_state
from src.services.parser.scraper import HHCaptchaRequiredError, HHScraper

logger = get_logger(__name__)

_DEFAULT_CONCURRENCY = 5


def _placeholder_negotiation_vacancy_dict(hid: str) -> dict:
    """Minimal vac dict when HH API has no vacancy (404). Still persisted for liked-feed merge."""
    url = f"https://hh.ru/vacancy/{hid}"
    return {
        "hh_vacancy_id": hid,
        "url": url,
        "title": "\u2014",
        "description": "",
        "orm_fields": {},
        "employer_data": {},
        "area_data": {},
        "company_name": None,
        "raw_skills": [],
        "_negotiations_placeholder": True,
    }


async def fetch_merged_vac_dicts_for_hh_ids(
    hh_ids: list[str],
    *,
    concurrency: int = _DEFAULT_CONCURRENCY,
    parse_mode: str | None = None,
    storage_state: dict | None = None,
) -> dict[str, dict]:
    """For each HH vacancy id, fetch vacancy detail and build merged dict like HHParserService.

    Uses public API JSON when *parse_mode* is ``api`` (default when
    ``settings.hh_api_vacancy_parsing_enabled`` is True), otherwise HTML via *storage_state*.
    When the fetch returns nothing (404), uses a minimal placeholder dict for persistence.
    Returns hh_vacancy_id -> vac dict.
    """
    if not hh_ids:
        return {}

    mode = (
        parse_mode
        if parse_mode is not None
        else ("api" if settings.hh_api_vacancy_parsing_enabled else "web")
    )

    scraper = HHScraper()
    sem = asyncio.Semaphore(concurrency)
    stop_requested = asyncio.Event()
    out: dict[str, dict] = {}

    client_kwargs: dict = {}
    if mode == "web" and storage_state:
        client_kwargs["cookies"] = httpx_cookies_from_storage_state(storage_state)
        client_kwargs["follow_redirects"] = True

    async def fetch_one(client: httpx.AsyncClient, hid: str) -> None:
        async with sem:
            if stop_requested.is_set():
                return
            url = f"https://hh.ru/vacancy/{hid}"
            try:
                page_data = await scraper.parse_vacancy_page(
                    client,
                    url,
                    parse_mode=mode,
                    storage_state=storage_state if mode == "api" else None,
                )
            except HHCaptchaRequiredError:
                stop_requested.set()
                logger.warning(
                    "negotiations_vacancy_fetch_captcha_abort",
                    hh_vacancy_id=hid,
                )
                raise
            except Exception as exc:
                logger.warning(
                    "negotiations_vacancy_fetch_error",
                    hh_vacancy_id=hid,
                    error=str(exc)[:200],
                )
                return
            if not page_data:
                logger.info(
                    "negotiations_vacancy_fetch_empty_placeholder",
                    hh_vacancy_id=hid,
                )
                out[hid] = _placeholder_negotiation_vacancy_dict(hid)
                return
            skills = page_data.get("skills", [])
            orm_fields = page_data.get("orm_fields", {})
            employer_data = page_data.get("employer_data", {})
            api_ctx = build_vacancy_api_context(orm_fields, employer_data, skills)
            merged: dict = {
                "hh_vacancy_id": hid,
                "url": url,
                **page_data,
                "raw_skills": skills,
                "vacancy_api_context": api_ctx,
            }
            merged.pop("skills", None)
            out[hid] = merged

    async with httpx.AsyncClient(**client_kwargs) as client:
        tasks = [asyncio.create_task(fetch_one(client, hid)) for hid in hh_ids]
        try:
            await asyncio.gather(*tasks)
        except HHCaptchaRequiredError:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    return out
