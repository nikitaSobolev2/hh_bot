from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.vacancy_feed import VacancyFeedSession
from src.repositories.base import BaseRepository


class VacancyFeedSessionRepository(BaseRepository[VacancyFeedSession]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, VacancyFeedSession)

    async def get_all_seen_vacancy_ids(self, user_id: int, company_id: int) -> set[int]:
        """Return all vacancy IDs from every feed session for this user and company."""
        stmt = select(VacancyFeedSession.vacancy_ids).where(
            VacancyFeedSession.user_id == user_id,
            VacancyFeedSession.autoparse_company_id == company_id,
        )
        result = await self._session.execute(stmt)
        seen: set[int] = set()
        for (ids,) in result:
            seen.update(ids)
        return seen
