"""Repository for CoverLetterVacancy model."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.cover_letter_vacancy import CoverLetterVacancy
from src.repositories.base import BaseRepository


class CoverLetterVacancyRepository(BaseRepository[CoverLetterVacancy]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, CoverLetterVacancy)

    async def get_by_hh_id(
        self, user_id: int, hh_vacancy_id: str
    ) -> CoverLetterVacancy | None:
        stmt = select(CoverLetterVacancy).where(
            CoverLetterVacancy.user_id == user_id,
            CoverLetterVacancy.hh_vacancy_id == hh_vacancy_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_or_update_from_api(
        self,
        user_id: int,
        hh_vacancy_id: str,
        url: str,
        title: str,
        company_name: str | None,
        description: str,
        raw_skills: list | None = None,
    ) -> CoverLetterVacancy:
        existing = await self.get_by_hh_id(user_id, hh_vacancy_id)
        if existing:
            await self.update(
                existing,
                url=url,
                title=title,
                company_name=company_name,
                description=description,
                raw_skills=raw_skills,
            )
            return existing
        return await self.create(
            user_id=user_id,
            hh_vacancy_id=hh_vacancy_id,
            url=url,
            title=title,
            company_name=company_name,
            description=description,
            raw_skills=raw_skills,
        )
