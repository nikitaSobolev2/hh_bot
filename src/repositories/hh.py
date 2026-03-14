"""Repositories for HH.ru reference models."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.hh import HHArea, HHEmployer
from src.repositories.base import BaseRepository


class HHEmployerRepository(BaseRepository[HHEmployer]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, HHEmployer)

    async def get_or_create_by_hh_id(self, employer_data: dict) -> HHEmployer:
        """Get existing employer by hh_employer_id or create new one."""
        hh_id = str(employer_data.get("id", ""))
        if not hh_id:
            raise ValueError("employer_data must contain 'id'")

        stmt = select(HHEmployer).where(HHEmployer.hh_employer_id == hh_id)
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        employer = HHEmployer(
            hh_employer_id=hh_id,
            name=employer_data.get("name", ""),
            url=employer_data.get("url"),
            alternate_url=employer_data.get("alternate_url"),
            logo_urls=employer_data.get("logo_urls"),
            vacancies_url=employer_data.get("vacancies_url"),
            accredited_it_employer=employer_data.get("accredited_it_employer", False),
            trusted=employer_data.get("trusted", False),
            is_identified_by_esia=employer_data.get("is_identified_by_esia"),
        )
        self._session.add(employer)
        await self._session.flush()
        return employer


class HHAreaRepository(BaseRepository[HHArea]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, HHArea)

    async def get_or_create_by_hh_id(self, area_data: dict) -> HHArea:
        """Get existing area by hh_area_id or create new one."""
        hh_id = str(area_data.get("id", ""))
        if not hh_id:
            raise ValueError("area_data must contain 'id'")

        stmt = select(HHArea).where(HHArea.hh_area_id == hh_id)
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        area = HHArea(
            hh_area_id=hh_id,
            name=area_data.get("name", ""),
            url=area_data.get("url"),
        )
        self._session.add(area)
        await self._session.flush()
        return area
