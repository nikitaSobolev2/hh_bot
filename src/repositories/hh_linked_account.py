from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.hh_linked_account import HhLinkedAccount
from src.repositories.base import BaseRepository


def _utc_naive_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


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

    async def update_resume_list_cache(
        self, account: HhLinkedAccount, items: list[dict[str, str]]
    ) -> HhLinkedAccount:
        return await self.update(
            account,
            resume_list_cache=items,
            resume_list_cached_at=_utc_naive_now(),
        )

    async def clear_resume_list_cache(self, account: HhLinkedAccount) -> HhLinkedAccount:
        return await self.update(
            account,
            resume_list_cache=None,
            resume_list_cached_at=None,
        )
