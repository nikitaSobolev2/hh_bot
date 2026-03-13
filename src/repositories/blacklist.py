from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.blacklist import VacancyBlacklist
from src.repositories.base import BaseRepository


def _utcnow_naive() -> datetime:
    """Return current UTC time as a naive datetime to match TIMESTAMP WITHOUT TIME ZONE columns."""
    return datetime.now(UTC).replace(tzinfo=None)


class BlacklistRepository(BaseRepository[VacancyBlacklist]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, VacancyBlacklist)

    async def get_active_ids(
        self,
        user_id: int,
        vacancy_title_context: str,
    ) -> set[str]:
        now = _utcnow_naive()
        stmt = select(VacancyBlacklist.hh_vacancy_id).where(
            VacancyBlacklist.user_id == user_id,
            VacancyBlacklist.vacancy_title_context == vacancy_title_context,
            VacancyBlacklist.blacklisted_until > now,
        )
        result = await self._session.execute(stmt)
        return set(result.scalars().all())

    async def count_active(self, user_id: int) -> int:
        now = _utcnow_naive()
        stmt = (
            select(func.count())
            .select_from(VacancyBlacklist)
            .where(
                VacancyBlacklist.user_id == user_id,
                VacancyBlacklist.blacklisted_until > now,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def get_contexts_with_counts(self, user_id: int) -> list[tuple[str, int]]:
        """Return (vacancy_title_context, count) for active blacklist entries."""
        now = _utcnow_naive()
        stmt = (
            select(
                VacancyBlacklist.vacancy_title_context,
                func.count(VacancyBlacklist.id).label("cnt"),
            )
            .where(
                VacancyBlacklist.user_id == user_id,
                VacancyBlacklist.blacklisted_until > now,
            )
            .group_by(VacancyBlacklist.vacancy_title_context)
        )
        result = await self._session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def clear_for_user(self, user_id: int) -> int:
        stmt = (
            delete(VacancyBlacklist)
            .where(VacancyBlacklist.user_id == user_id)
            .returning(VacancyBlacklist.id)
        )
        result = await self._session.execute(stmt)
        return len(result.all())

    async def clear_by_context(self, user_id: int, vacancy_title_context: str) -> int:
        """Clear blacklist entries matching a context prefix.

        Uses startswith (LIKE 'prefix%') to handle callback_data
        truncation — the callback passes up to 50 chars, but DB
        stores the full title (up to 500 chars).
        """
        stmt = (
            delete(VacancyBlacklist)
            .where(
                VacancyBlacklist.user_id == user_id,
                VacancyBlacklist.vacancy_title_context.startswith(vacancy_title_context),
            )
            .returning(VacancyBlacklist.id)
        )
        result = await self._session.execute(stmt)
        return len(result.all())
