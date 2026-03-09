from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.parsing import AggregatedResult, ParsedVacancy, ParsingCompany
from src.repositories.base import BaseRepository


class ParsingCompanyRepository(BaseRepository[ParsingCompany]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ParsingCompany)

    async def get_by_user(
        self,
        user_id: int,
        *,
        offset: int = 0,
        limit: int = 10,
    ) -> list[ParsingCompany]:
        stmt = (
            select(ParsingCompany)
            .where(ParsingCompany.user_id == user_id)
            .order_by(ParsingCompany.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_with_details(self, company_id: int) -> ParsingCompany | None:
        stmt = (
            select(ParsingCompany)
            .options(selectinload(ParsingCompany.vacancies))
            .options(selectinload(ParsingCompany.aggregated_result))
            .where(ParsingCompany.id == company_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_by_user(self, user_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(ParsingCompany)
            .where(ParsingCompany.user_id == user_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()


class ParsedVacancyRepository(BaseRepository[ParsedVacancy]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ParsedVacancy)

    async def exists_by_hh_id(self, hh_vacancy_id: str) -> bool:
        stmt = select(
            select(ParsedVacancy.id).where(ParsedVacancy.hh_vacancy_id == hh_vacancy_id).exists()
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def get_by_hh_id(self, hh_vacancy_id: str) -> ParsedVacancy | None:
        stmt = select(ParsedVacancy).where(ParsedVacancy.hh_vacancy_id == hh_vacancy_id)
        result = await self._session.execute(stmt)
        return result.scalars().first()


class AggregatedResultRepository(BaseRepository[AggregatedResult]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AggregatedResult)

    async def get_by_company(self, parsing_company_id: int) -> AggregatedResult | None:
        stmt = select(AggregatedResult).where(
            AggregatedResult.parsing_company_id == parsing_company_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
