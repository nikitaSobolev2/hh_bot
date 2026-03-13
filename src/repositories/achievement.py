"""Repository for achievement generation models."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.achievement import AchievementGeneration, AchievementGenerationItem
from src.repositories.base import BaseRepository

_PAGE_SIZE = 5


@dataclass(frozen=True)
class AchievementItemData:
    """Typed input for bulk creation of achievement items."""

    company_name: str
    work_experience_id: int | None = None
    user_achievements_input: str | None = None
    user_responsibilities_input: str | None = None


class AchievementGenerationRepository(BaseRepository[AchievementGeneration]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AchievementGeneration)

    async def create_for_user(self, user_id: int) -> AchievementGeneration:
        generation = AchievementGeneration(user_id=user_id)
        self._session.add(generation)
        await self._session.flush()
        return generation

    async def get_by_id(self, generation_id: int) -> AchievementGeneration | None:
        result = await self._session.execute(
            select(AchievementGeneration)
            .where(AchievementGeneration.id == generation_id)
            .options(
                selectinload(AchievementGeneration.items).selectinload(
                    AchievementGenerationItem.work_experience
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_user_paginated(
        self,
        user_id: int,
        page: int = 0,
    ) -> tuple[list[AchievementGeneration], int]:
        base_where = (
            AchievementGeneration.user_id == user_id,
            AchievementGeneration.is_deleted.is_(False),
        )

        count_stmt = select(func.count()).select_from(AchievementGeneration).where(*base_where)
        total = await self._session.scalar(count_stmt) or 0

        result = await self._session.execute(
            select(AchievementGeneration)
            .where(*base_where)
            .order_by(AchievementGeneration.created_at.desc())
            .offset(page * _PAGE_SIZE)
            .limit(_PAGE_SIZE)
            .options(selectinload(AchievementGeneration.items))
        )
        return list(result.scalars().all()), total

    async def update_status(self, generation: AchievementGeneration, status: str) -> None:
        generation.status = status
        await self._session.flush()

    async def soft_delete(self, generation: AchievementGeneration) -> None:
        generation.is_deleted = True
        await self._session.flush()


class AchievementItemRepository(BaseRepository[AchievementGenerationItem]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AchievementGenerationItem)

    async def create_bulk(
        self,
        generation_id: int,
        items: list[AchievementItemData],
    ) -> list[AchievementGenerationItem]:
        created = []
        for idx, item_data in enumerate(items):
            item = AchievementGenerationItem(
                generation_id=generation_id,
                work_experience_id=item_data.work_experience_id,
                company_name=item_data.company_name,
                user_achievements_input=item_data.user_achievements_input,
                user_responsibilities_input=item_data.user_responsibilities_input,
                sort_order=idx,
            )
            self._session.add(item)
            created.append(item)
        await self._session.flush()
        return created

    async def update_generated_text(self, item: AchievementGenerationItem, text: str) -> None:
        item.generated_text = text
        await self._session.flush()

    async def get_by_generation(self, generation_id: int) -> list[AchievementGenerationItem]:
        result = await self._session.execute(
            select(AchievementGenerationItem)
            .where(AchievementGenerationItem.generation_id == generation_id)
            .order_by(AchievementGenerationItem.sort_order)
        )
        return list(result.scalars().all())
