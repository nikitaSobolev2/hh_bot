from datetime import datetime

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

    async def list_for_feed_session_summary(
        self,
        user_id: int,
        vacancy_ids: list[int],
        since: datetime,
    ) -> list[HhApplicationAttempt]:
        """Latest attempt per vacancy (by created_at desc) within feed session scope."""
        if not vacancy_ids:
            return []
        stmt = (
            select(HhApplicationAttempt)
            .where(
                HhApplicationAttempt.user_id == user_id,
                HhApplicationAttempt.autoparsed_vacancy_id.in_(vacancy_ids),
                HhApplicationAttempt.created_at >= since,
            )
            .order_by(HhApplicationAttempt.created_at.desc())
        )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        seen: set[int] = set()
        out: list[HhApplicationAttempt] = []
        for a in rows:
            vid = a.autoparsed_vacancy_id
            if vid is None or vid in seen:
                continue
            seen.add(vid)
            out.append(a)
        return out
