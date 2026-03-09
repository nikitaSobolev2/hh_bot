from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.autoparse import AutoparseCompany, AutoparsedVacancy
from src.repositories.base import BaseRepository


class AutoparseCompanyRepository(BaseRepository[AutoparseCompany]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AutoparseCompany)

    async def get_by_user(
        self,
        user_id: int,
        *,
        offset: int = 0,
        limit: int = 10,
    ) -> list[AutoparseCompany]:
        stmt = (
            select(AutoparseCompany)
            .where(
                AutoparseCompany.user_id == user_id,
                AutoparseCompany.is_deleted.is_(False),
            )
            .order_by(AutoparseCompany.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_user(self, user_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(AutoparseCompany)
            .where(
                AutoparseCompany.user_id == user_id,
                AutoparseCompany.is_deleted.is_(False),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def get_all_enabled(self) -> Sequence[AutoparseCompany]:
        stmt = select(AutoparseCompany).where(
            AutoparseCompany.is_enabled.is_(True),
            AutoparseCompany.is_deleted.is_(False),
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def soft_delete(self, company_id: int) -> None:
        company = await self.get_by_id(company_id)
        if company:
            await self.update(company, is_deleted=True, is_enabled=False)

    async def toggle(self, company: AutoparseCompany) -> bool:
        new_state = not company.is_enabled
        await self.update(company, is_enabled=new_state)
        return new_state


class AutoparsedVacancyRepository(BaseRepository[AutoparsedVacancy]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AutoparsedVacancy)

    async def get_by_company(
        self,
        company_id: int,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> list[AutoparsedVacancy]:
        stmt = (
            select(AutoparsedVacancy)
            .where(AutoparsedVacancy.autoparse_company_id == company_id)
            .order_by(AutoparsedVacancy.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_company(self, company_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(AutoparsedVacancy)
            .where(AutoparsedVacancy.autoparse_company_id == company_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def get_all_by_company(self, company_id: int) -> list[AutoparsedVacancy]:
        stmt = (
            select(AutoparsedVacancy)
            .where(AutoparsedVacancy.autoparse_company_id == company_id)
            .order_by(AutoparsedVacancy.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def exists_by_hh_id(self, hh_vacancy_id: str) -> bool:
        stmt = select(
            select(AutoparsedVacancy.id)
            .where(AutoparsedVacancy.hh_vacancy_id == hh_vacancy_id)
            .exists()
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def get_by_hh_id(self, hh_vacancy_id: str) -> AutoparsedVacancy | None:
        stmt = select(AutoparsedVacancy).where(AutoparsedVacancy.hh_vacancy_id == hh_vacancy_id)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_known_hh_ids_for_company(self, company_id: int) -> set[str]:
        stmt = select(AutoparsedVacancy.hh_vacancy_id).where(
            AutoparsedVacancy.autoparse_company_id == company_id
        )
        result = await self._session.execute(stmt)
        return set(result.scalars().all())

    async def get_all_known_hh_ids(self) -> set[str]:
        stmt = select(AutoparsedVacancy.hh_vacancy_id).distinct()
        result = await self._session.execute(stmt)
        return set(result.scalars().all())

    async def get_new_since(
        self,
        company_id: int,
        since: datetime,
        min_compat: float,
        *,
        limit: int = 100,
    ) -> list[AutoparsedVacancy]:
        stmt = (
            select(AutoparsedVacancy)
            .where(
                AutoparsedVacancy.autoparse_company_id == company_id,
                AutoparsedVacancy.created_at > since,
                or_(
                    AutoparsedVacancy.compatibility_score.is_(None),
                    AutoparsedVacancy.compatibility_score >= min_compat,
                ),
            )
            .order_by(AutoparsedVacancy.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
