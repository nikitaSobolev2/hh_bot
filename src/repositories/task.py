from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.task import (
    BaseCeleryTask,
    CompanyCreateKeyPhrasesTask,
    CompanyParseKeywordsFromDescriptionTask,
)
from src.repositories.base import BaseRepository


class CeleryTaskRepository(BaseRepository[BaseCeleryTask]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, BaseCeleryTask)

    async def delete_by_idempotency_key(self, key: str) -> bool:
        """Delete task by idempotency key. Returns True if a row was deleted."""
        existing = await self.get_by_idempotency_key(key)
        if existing:
            await self.delete_by_id(existing.id)
            return True
        return False

    async def get_by_idempotency_key(self, key: str) -> BaseCeleryTask | None:
        stmt = select(BaseCeleryTask).where(BaseCeleryTask.idempotency_key == key)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_celery_id(self, celery_task_id: str) -> BaseCeleryTask | None:
        stmt = select(BaseCeleryTask).where(BaseCeleryTask.celery_task_id == celery_task_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user(
        self,
        user_id: int,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> list[BaseCeleryTask]:
        stmt = (
            select(BaseCeleryTask)
            .where(BaseCeleryTask.user_id == user_id)
            .order_by(BaseCeleryTask.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_cover_letter_tasks_by_user(
        self,
        user_id: int,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> list[BaseCeleryTask]:
        stmt = (
            select(BaseCeleryTask)
            .where(
                BaseCeleryTask.user_id == user_id,
                BaseCeleryTask.task_type == "cover_letter",
                BaseCeleryTask.status == "completed",
            )
            .order_by(BaseCeleryTask.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_cover_letter_tasks_by_user(self, user_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(BaseCeleryTask)
            .where(
                BaseCeleryTask.user_id == user_id,
                BaseCeleryTask.task_type == "cover_letter",
                BaseCeleryTask.status == "completed",
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()


class ParseKeywordsTaskRepository(BaseRepository[CompanyParseKeywordsFromDescriptionTask]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, CompanyParseKeywordsFromDescriptionTask)

    async def get_by_company(
        self,
        parsing_company_id: int,
    ) -> list[CompanyParseKeywordsFromDescriptionTask]:
        stmt = select(CompanyParseKeywordsFromDescriptionTask).where(
            CompanyParseKeywordsFromDescriptionTask.parsing_company_id == parsing_company_id
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class CreateKeyPhrasesTaskRepository(BaseRepository[CompanyCreateKeyPhrasesTask]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, CompanyCreateKeyPhrasesTask)
