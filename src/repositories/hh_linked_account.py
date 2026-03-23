from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.hh_linked_account import HhLinkedAccount
from src.repositories.base import BaseRepository


class HhLinkedAccountRepository(BaseRepository[HhLinkedAccount]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, HhLinkedAccount)

    async def list_active_for_user(self, user_id: int) -> list[HhLinkedAccount]:
        stmt = (
            select(HhLinkedAccount)
            .where(
                HhLinkedAccount.user_id == user_id,
                HhLinkedAccount.revoked_at.is_(None),
            )
            .order_by(HhLinkedAccount.id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_user_and_hh_user_id(
        self, user_id: int, hh_user_id: str
    ) -> HhLinkedAccount | None:
        stmt = select(HhLinkedAccount).where(
            HhLinkedAccount.user_id == user_id,
            HhLinkedAccount.hh_user_id == hh_user_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
