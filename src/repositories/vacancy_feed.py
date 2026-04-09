from sqlalchemy import delete, distinct, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.vacancy_feed import VacancyFeedSession
from src.repositories.base import BaseRepository


class VacancyFeedSessionRepository(BaseRepository[VacancyFeedSession]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, VacancyFeedSession)

    async def list_sessions_for_user_company(
        self,
        user_id: int,
        company_id: int,
    ) -> list[VacancyFeedSession]:
        stmt = select(VacancyFeedSession).where(
            VacancyFeedSession.user_id == user_id,
            VacancyFeedSession.autoparse_company_id == company_id,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_seen_vacancy_ids(self, user_id: int, company_id: int) -> set[int]:
        """Return all vacancy IDs queued in any feed session for this user and company.

        Includes vacancies that were queued but never reacted to.  Use
        get_all_reacted_vacancy_ids when you only want truly-reviewed IDs.
        """
        stmt = select(VacancyFeedSession.vacancy_ids).where(
            VacancyFeedSession.user_id == user_id,
            VacancyFeedSession.autoparse_company_id == company_id,
        )
        result = await self._session.execute(stmt)
        seen: set[int] = set()
        for (ids,) in result:
            seen.update(ids)
        return seen

    async def get_all_reacted_vacancy_ids(self, user_id: int, company_id: int) -> set[int]:
        """Return IDs of vacancies the user has explicitly liked or disliked.

        Unlike get_all_seen_vacancy_ids this excludes vacancies that were
        queued in a session but never reached via the feed (e.g. the user
        stopped early).
        """
        stmt = select(
            VacancyFeedSession.liked_ids,
            VacancyFeedSession.disliked_ids,
        ).where(
            VacancyFeedSession.user_id == user_id,
            VacancyFeedSession.autoparse_company_id == company_id,
        )
        result = await self._session.execute(stmt)
        reacted: set[int] = set()
        for liked, disliked in result:
            reacted.update(liked)
            reacted.update(disliked)
        return reacted

    async def get_all_liked_vacancy_ids_for_user(self, user_id: int) -> set[int]:
        """Return unique vacancy IDs the user has liked across all autoparse companies."""
        stmt = select(VacancyFeedSession.liked_ids).where(
            VacancyFeedSession.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        liked: set[int] = set()
        for (ids,) in result:
            liked.update(ids)
        return liked

    async def get_liked_vacancy_page_for_user(
        self,
        user_id: int,
        *,
        offset: int = 0,
        limit: int = 15,
    ) -> tuple[list[int], int]:
        return await self._get_distinct_user_reaction_page(
            user_id,
            VacancyFeedSession.liked_ids,
            offset=offset,
            limit=limit,
        )

    async def get_all_disliked_vacancy_ids_for_user(self, user_id: int) -> set[int]:
        """Return unique vacancy IDs the user has disliked across all autoparse companies."""
        stmt = select(VacancyFeedSession.disliked_ids).where(
            VacancyFeedSession.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        disliked: set[int] = set()
        for (ids,) in result:
            disliked.update(ids)
        return disliked

    async def get_disliked_vacancy_page_for_user(
        self,
        user_id: int,
        *,
        offset: int = 0,
        limit: int = 15,
    ) -> tuple[list[int], int]:
        return await self._get_distinct_user_reaction_page(
            user_id,
            VacancyFeedSession.disliked_ids,
            offset=offset,
            limit=limit,
        )

    async def get_liked_vacancy_ids_for_user_company(
        self, user_id: int, company_id: int
    ) -> set[int]:
        stmt = select(VacancyFeedSession.liked_ids).where(
            VacancyFeedSession.user_id == user_id,
            VacancyFeedSession.autoparse_company_id == company_id,
        )
        result = await self._session.execute(stmt)
        liked: set[int] = set()
        for (ids,) in result:
            liked.update(ids)
        return liked

    async def get_disliked_vacancy_ids_for_user_company(
        self, user_id: int, company_id: int
    ) -> set[int]:
        stmt = select(VacancyFeedSession.disliked_ids).where(
            VacancyFeedSession.user_id == user_id,
            VacancyFeedSession.autoparse_company_id == company_id,
        )
        result = await self._session.execute(stmt)
        disliked: set[int] = set()
        for (ids,) in result:
            disliked.update(ids)
        return disliked

    async def clear_liked_ids_for_user_company(self, user_id: int, company_id: int) -> None:
        stmt = (
            update(VacancyFeedSession)
            .where(
                VacancyFeedSession.user_id == user_id,
                VacancyFeedSession.autoparse_company_id == company_id,
            )
            .values(liked_ids=[])
        )
        await self._session.execute(stmt)

    async def clear_disliked_ids_for_user_company(self, user_id: int, company_id: int) -> None:
        stmt = (
            update(VacancyFeedSession)
            .where(
                VacancyFeedSession.user_id == user_id,
                VacancyFeedSession.autoparse_company_id == company_id,
            )
            .values(disliked_ids=[])
        )
        await self._session.execute(stmt)

    async def delete_all_for_company(self, company_id: int) -> None:
        stmt = delete(VacancyFeedSession).where(
            VacancyFeedSession.autoparse_company_id == company_id,
        )
        await self._session.execute(stmt)

    async def _get_distinct_user_reaction_page(
        self,
        user_id: int,
        reaction_column,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[int], int]:
        reaction_ids = (
            select(func.unnest(reaction_column).label("vacancy_id"))
            .where(VacancyFeedSession.user_id == user_id)
            .subquery()
        )
        total_stmt = select(func.count(distinct(reaction_ids.c.vacancy_id)))
        page_stmt = (
            select(reaction_ids.c.vacancy_id)
            .distinct()
            .order_by(reaction_ids.c.vacancy_id.desc())
            .offset(offset)
            .limit(limit)
        )
        total_result = await self._session.execute(total_stmt)
        page_result = await self._session.execute(page_stmt)
        return list(page_result.scalars().all()), int(total_result.scalar() or 0)
