from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import User
from src.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_referral_code(self, referral_code: str) -> User | None:
        stmt = select(User).where(User.referral_code == referral_code)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def search(
        self,
        *,
        query: str = "",
        offset: int = 0,
        limit: int = 20,
    ) -> list[User]:
        stmt = select(User)
        if query:
            if query.isdigit():
                stmt = stmt.where(User.telegram_id == int(query))
            else:
                pattern = f"%{query}%"
                stmt = stmt.where(
                    User.username.ilike(pattern)
                    | User.first_name.ilike(pattern)
                    | User.last_name.ilike(pattern)
                )
        stmt = stmt.offset(offset).limit(limit).order_by(User.id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
