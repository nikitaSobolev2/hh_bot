from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.autoparse import (
    NEGOTIATIONS_SYNC_PLACEHOLDER_COMPAT,
    AutoparseCompany,
    AutoparsedVacancy,
)
from src.repositories.base import BaseRepository


def feed_vacancy_newest_first_key(v: AutoparsedVacancy) -> tuple:
    """Sort key: newest HH published_at first; missing date last, then id desc."""
    if v.published_at is not None:
        return (0, -v.published_at.timestamp(), -v.id)
    return (1, -v.id)


def _feed_order_by_clause() -> tuple:
    """SQL ``ORDER BY``: HH publication time (newest first), then primary key."""
    return (
        AutoparsedVacancy.published_at.desc().nulls_last(),
        AutoparsedVacancy.id.desc(),
    )


def _exclude_negotiations_placeholder_compat():
    """Stub rows from negotiations sync (HH 404) use compatibility_score = -1."""
    return or_(
        AutoparsedVacancy.compatibility_score.is_(None),
        AutoparsedVacancy.compatibility_score != NEGOTIATIONS_SYNC_PLACEHOLDER_COMPAT,
    )


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

    async def get_by_id_for_user(
        self,
        company_id: int,
        user_id: int,
    ) -> AutoparseCompany | None:
        stmt = select(AutoparseCompany).where(
            AutoparseCompany.id == company_id,
            AutoparseCompany.user_id == user_id,
            AutoparseCompany.is_deleted.is_(False),
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_all_enabled(self) -> Sequence[AutoparseCompany]:
        stmt = select(AutoparseCompany).where(
            AutoparseCompany.is_enabled.is_(True),
            AutoparseCompany.is_deleted.is_(False),
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_due_for_dispatch(self, interval_hours: int) -> Sequence[AutoparseCompany]:
        """Return enabled companies whose last parse is older than interval_hours, or never ran."""
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=interval_hours)
        stmt = select(AutoparseCompany).where(
            AutoparseCompany.is_enabled.is_(True),
            AutoparseCompany.is_deleted.is_(False),
            or_(
                AutoparseCompany.last_parsed_at.is_(None),
                AutoparseCompany.last_parsed_at <= cutoff,
            ),
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def soft_delete(self, company_id: int, user_id: int | None = None) -> None:
        company = (
            await self.get_by_id_for_user(company_id, user_id)
            if user_id is not None
            else await self.get_by_id(company_id)
        )
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
            .order_by(*_feed_order_by_clause())
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
            .order_by(*_feed_order_by_clause())
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

    async def get_by_company_hh_id(
        self,
        company_id: int,
        hh_vacancy_id: str,
    ) -> AutoparsedVacancy | None:
        stmt = select(AutoparsedVacancy).where(
            AutoparsedVacancy.autoparse_company_id == company_id,
            AutoparsedVacancy.hh_vacancy_id == hh_vacancy_id,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_by_hh_id_with_employer(self, hh_vacancy_id: str) -> AutoparsedVacancy | None:
        stmt = (
            select(AutoparsedVacancy)
            .options(selectinload(AutoparsedVacancy.employer))
            .where(AutoparsedVacancy.hh_vacancy_id == hh_vacancy_id)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_by_company_hh_id_with_employer(
        self,
        company_id: int,
        hh_vacancy_id: str,
    ) -> AutoparsedVacancy | None:
        stmt = (
            select(AutoparsedVacancy)
            .options(selectinload(AutoparsedVacancy.employer))
            .where(
                AutoparsedVacancy.autoparse_company_id == company_id,
                AutoparsedVacancy.hh_vacancy_id == hh_vacancy_id,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_known_hh_ids_for_company(self, company_id: int) -> set[str]:
        stmt = select(AutoparsedVacancy.hh_vacancy_id).where(
            AutoparsedVacancy.autoparse_company_id == company_id
        )
        result = await self._session.execute(stmt)
        return set(result.scalars().all())

    async def list_ids_by_company_and_hh_vacancy_ids(
        self,
        company_id: int,
        hh_vacancy_ids: set[str],
    ) -> list[int]:
        """Autoparsed vacancy PKs for this company whose hh_vacancy_id is in *hh_vacancy_ids*."""
        if not hh_vacancy_ids:
            return []
        stmt = select(AutoparsedVacancy.id).where(
            AutoparsedVacancy.autoparse_company_id == company_id,
            AutoparsedVacancy.hh_vacancy_id.in_(list(hh_vacancy_ids)),
        )
        result = await self._session.execute(stmt)
        return [int(x) for x in result.scalars().all()]

    async def hh_vacancy_ids_already_in_company(
        self,
        company_id: int,
        hh_vacancy_ids: set[str],
    ) -> set[str]:
        """Subset of *hh_vacancy_ids* that already exist for this autoparse company."""
        if not hh_vacancy_ids:
            return set()
        stmt = select(AutoparsedVacancy.hh_vacancy_id).where(
            AutoparsedVacancy.autoparse_company_id == company_id,
            AutoparsedVacancy.hh_vacancy_id.in_(list(hh_vacancy_ids)),
        )
        result = await self._session.execute(stmt)
        return {str(x) for x in result.scalars().all() if x is not None}

    async def get_all_known_hh_ids(self) -> set[str]:
        stmt = select(AutoparsedVacancy.hh_vacancy_id).distinct()
        result = await self._session.execute(stmt)
        return set(result.scalars().all())

    async def delete_all_by_company(self, company_id: int) -> None:
        stmt = delete(AutoparsedVacancy).where(
            AutoparsedVacancy.autoparse_company_id == company_id,
        )
        await self._session.execute(stmt)

    async def get_by_ids(
        self,
        ids: list[int],
        min_compat: float,
    ) -> list[AutoparsedVacancy]:
        """Fetch vacancies by primary-key list, keeping those meeting min_compat."""
        if not ids:
            return []
        stmt = (
            select(AutoparsedVacancy)
            .where(
                AutoparsedVacancy.id.in_(ids),
                or_(
                    AutoparsedVacancy.compatibility_score.is_(None),
                    AutoparsedVacancy.compatibility_score >= min_compat,
                ),
            )
            .order_by(*_feed_order_by_clause())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_ids_simple(self, ids: list[int]) -> list[AutoparsedVacancy]:
        """Fetch vacancies by primary-key list without compatibility filter."""
        if not ids:
            return []
        stmt = select(AutoparsedVacancy).where(
            AutoparsedVacancy.id.in_(ids),
        ).order_by(*_feed_order_by_clause())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_ids_for_company(
        self,
        company_id: int,
        ids: list[int],
    ) -> list[AutoparsedVacancy]:
        """Fetch vacancies by PK list scoped to a company; preserve *ids* order."""
        if not ids:
            return []
        stmt = select(AutoparsedVacancy).where(
            AutoparsedVacancy.id.in_(ids),
            AutoparsedVacancy.autoparse_company_id == company_id,
        )
        result = await self._session.execute(stmt)
        by_id = {v.id: v for v in result.scalars().all()}
        return [by_id[i] for i in ids if i in by_id]

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
                AutoparsedVacancy.created_at >= since,
                or_(
                    AutoparsedVacancy.compatibility_score.is_(None),
                    AutoparsedVacancy.compatibility_score >= min_compat,
                ),
            )
            .order_by(*_feed_order_by_clause())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_unseen_for_user(
        self,
        user_id: int,
        exclude_vacancy_ids: set[int],
        *,
        limit: int = 200,
    ) -> list[AutoparsedVacancy]:
        """Return vacancies from all user's autoparse companies not in exclude_vacancy_ids."""
        stmt = (
            select(AutoparsedVacancy)
            .options(selectinload(AutoparsedVacancy.employer))
            .join(AutoparseCompany, AutoparsedVacancy.autoparse_company_id == AutoparseCompany.id)
            .where(
                AutoparseCompany.user_id == user_id,
                AutoparseCompany.is_deleted.is_(False),
                _exclude_negotiations_placeholder_compat(),
            )
            .order_by(*_feed_order_by_clause())
            .limit(limit)
        )
        if exclude_vacancy_ids:
            stmt = stmt.where(AutoparsedVacancy.id.notin_(exclude_vacancy_ids))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_below_min_compat_for_user(
        self,
        user_id: int,
        min_compat: float,
        exclude_vacancy_ids: set[int],
        *,
        limit: int = 100,
    ) -> list[AutoparsedVacancy]:
        """Return vacancies below min_compat or with null score for user's companies."""
        stmt = (
            select(AutoparsedVacancy)
            .join(AutoparseCompany, AutoparsedVacancy.autoparse_company_id == AutoparseCompany.id)
            .where(
                AutoparseCompany.user_id == user_id,
                AutoparseCompany.is_deleted.is_(False),
                and_(
                    or_(
                        AutoparsedVacancy.compatibility_score.is_(None),
                        AutoparsedVacancy.compatibility_score < min_compat,
                    ),
                    _exclude_negotiations_placeholder_compat(),
                ),
            )
            .order_by(*_feed_order_by_clause())
            .limit(limit)
        )
        if exclude_vacancy_ids:
            stmt = stmt.where(AutoparsedVacancy.id.notin_(exclude_vacancy_ids))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
