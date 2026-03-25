"""Fetch HH vacancy JSON (public API) and build vac dicts for AutoparsedVacancy rows."""

from __future__ import annotations

import asyncio

import httpx

from src.core.logging import get_logger
from src.schemas.vacancy import build_vacancy_api_context
from src.services.parser.scraper import HHScraper

logger = get_logger(__name__)

_DEFAULT_CONCURRENCY = 5


async def fetch_merged_vac_dicts_for_hh_ids(
    hh_ids: list[str],
    *,
    concurrency: int = _DEFAULT_CONCURRENCY,
) -> dict[str, dict]:
    """For each HH vacancy id, GET api.hh.ru vacancy and build merged dict like HHParserService.

    Skips ids where the API returns nothing. Returns hh_vacancy_id -> vac dict.
    """
    if not hh_ids:
        return {}

    scraper = HHScraper()
    sem = asyncio.Semaphore(concurrency)
    out: dict[str, dict] = {}

    async def fetch_one(client: httpx.AsyncClient, hid: str) -> None:
        async with sem:
            url = f"https://hh.ru/vacancy/{hid}"
            try:
                page_data = await scraper.parse_vacancy_page(client, url)
            except Exception as exc:
                logger.warning(
                    "negotiations_vacancy_fetch_error",
                    hh_vacancy_id=hid,
                    error=str(exc)[:200],
                )
                return
            if not page_data:
                logger.info("negotiations_vacancy_fetch_empty", hh_vacancy_id=hid)
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

    async with httpx.AsyncClient() as client:
        await asyncio.gather(*[fetch_one(client, hid) for hid in hh_ids])

    return out
