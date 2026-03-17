"""Services for cover letter module: URL parsing and vacancy fetch."""

from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.cover_letter_vacancy import CoverLetterVacancy
from src.repositories.cover_letter_vacancy import CoverLetterVacancyRepository
from src.services.parser.scraper import HHScraper


def parse_hh_vacancy_id(url: str) -> str | None:
    """Extract HH vacancy ID from URL. Returns None if not a valid HH vacancy URL."""
    return HHScraper._extract_vacancy_id(url)


async def fetch_and_upsert_vacancy(
    session: AsyncSession,
    user_id: int,
    url: str,
) -> CoverLetterVacancy | None:
    """Fetch vacancy from HH API and upsert into cover_letter_vacancies.

    Returns CoverLetterVacancy on success, None if URL is invalid or fetch fails.
    """
    hh_vacancy_id = parse_hh_vacancy_id(url)
    if not hh_vacancy_id:
        return None

    scraper = HHScraper()
    async with httpx.AsyncClient() as client:
        page_data = await scraper.parse_vacancy_page(client, url)

    if not page_data:
        return None

    title = page_data.get("title", "") or ""
    company_name = page_data.get("company_name") or ""
    description = page_data.get("description", "") or ""
    skills = page_data.get("skills")
    raw_skills = list(skills) if isinstance(skills, list) else None

    repo = CoverLetterVacancyRepository(session)
    return await repo.create_or_update_from_api(
        user_id=user_id,
        hh_vacancy_id=hh_vacancy_id,
        url=url,
        title=title,
        company_name=company_name or None,
        description=description,
        raw_skills=raw_skills,
    )
