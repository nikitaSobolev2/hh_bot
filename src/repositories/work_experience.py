from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.work_experience import UserWorkExperience
from src.repositories.base import BaseRepository


class WorkExperienceRepository(BaseRepository[UserWorkExperience]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, UserWorkExperience)

    async def get_active_by_user(self, user_id: int) -> list[UserWorkExperience]:
        stmt = (
            select(UserWorkExperience)
            .where(
                UserWorkExperience.user_id == user_id,
                UserWorkExperience.is_active.is_(True),
            )
            .order_by(UserWorkExperience.created_at)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_active_by_user(self, user_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(UserWorkExperience)
            .where(
                UserWorkExperience.user_id == user_id,
                UserWorkExperience.is_active.is_(True),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def deactivate(self, work_exp_id: int, user_id: int) -> bool:
        entity = await self.get_by_id(work_exp_id)
        if not entity or entity.user_id != user_id:
            return False
        entity.is_active = False
        await self._session.flush()
        return True
