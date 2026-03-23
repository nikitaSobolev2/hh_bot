from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.hh_application_attempt import HhApplicationAttempt
from src.repositories.base import BaseRepository


class HhApplicationAttemptRepository(BaseRepository[HhApplicationAttempt]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, HhApplicationAttempt)

    async def has_successful_apply(
        self,
        user_id: int,
        hh_vacancy_id: str,
        resume_id: str,
    ) -> bool:
        stmt = (
            select(func.count())
            .select_from(HhApplicationAttempt)
            .where(
                HhApplicationAttempt.user_id == user_id,
                HhApplicationAttempt.hh_vacancy_id == hh_vacancy_id,
                HhApplicationAttempt.resume_id == resume_id,
                HhApplicationAttempt.status == "success",
            )
        )
        result = await self._session.execute(stmt)
        return (result.scalar_one() or 0) > 0
