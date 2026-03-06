from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.base import Base


class BaseRepository[T: Base]:
    def __init__(self, session: AsyncSession, model: type[T]) -> None:
        self._session = session
        self._model = model

    async def get_by_id(self, entity_id: int) -> T | None:
        return await self._session.get(self._model, entity_id)

    async def get_all(self, *, offset: int = 0, limit: int = 100) -> Sequence[T]:
        stmt = select(self._model).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def create(self, **kwargs) -> T:
        instance = self._model(**kwargs)
        self._session.add(instance)
        await self._session.flush()
        return instance

    async def update(self, entity: T, **kwargs) -> T:
        for key, value in kwargs.items():
            setattr(entity, key, value)
        await self._session.flush()
        return entity

    async def delete_by_id(self, entity_id: int) -> None:
        stmt = delete(self._model).where(self._model.id == entity_id)
        await self._session.execute(stmt)

    async def count(self) -> int:
        stmt = select(func.count()).select_from(self._model)
        result = await self._session.execute(stmt)
        return result.scalar_one()
