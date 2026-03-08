from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.ban import UserBan
from src.repositories.base import BaseRepository


class UserBanRepository(BaseRepository[UserBan]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, UserBan)

    async def get_active_ban(self, user_id: int) -> UserBan | None:
        stmt = (
            select(UserBan)
            .where(UserBan.user_id == user_id, UserBan.is_active.is_(True))
            .order_by(UserBan.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_ban_history(
        self,
        user_id: int,
        *,
        limit: int = 20,
    ) -> Sequence[UserBan]:
        stmt = (
            select(UserBan)
            .where(UserBan.user_id == user_id)
            .order_by(UserBan.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def create_ban(
        self,
        *,
        user_id: int,
        admin_id: int,
        reason: str,
        banned_until: datetime | None = None,
        ticket_id: int | None = None,
    ) -> UserBan:
        await self.deactivate_bans(user_id)
        return await self.create(
            user_id=user_id,
            admin_id=admin_id,
            reason=reason,
            banned_until=banned_until,
            ticket_id=ticket_id,
        )

    async def deactivate_bans(self, user_id: int) -> int:
        stmt = (
            update(UserBan)
            .where(UserBan.user_id == user_id, UserBan.is_active.is_(True))
            .values(is_active=False)
        )
        result = await self._session.execute(stmt)
        return result.rowcount
