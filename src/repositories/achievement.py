"""Repository for achievement generation models."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.achievement import AchievementGeneration, AchievementGenerationItem

_PAGE_SIZE = 5


class AchievementGenerationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_id: int) -> AchievementGeneration:
        generation = AchievementGeneration(user_id=user_id)
        self._session.add(generation)
        await self._session.flush()
        return generation

    async def get_by_id(self, generation_id: int) -> AchievementGeneration | None:
        result = await self._session.execute(
            select(AchievementGeneration)
            .where(AchievementGeneration.id == generation_id)
            .options(selectinload(AchievementGeneration.items))
        )
        return result.scalar_one_or_none()

    async def get_by_user_paginated(
        self,
        user_id: int,
        page: int = 0,
    ) -> tuple[list[AchievementGeneration], int]:
        count_result = await self._session.execute(
            select(AchievementGeneration).where(
                AchievementGeneration.user_id == user_id,
                AchievementGeneration.is_deleted.is_(False),
            )
        )
        all_rows = count_result.scalars().all()
        total = len(all_rows)

        result = await self._session.execute(
            select(AchievementGeneration)
            .where(
                AchievementGeneration.user_id == user_id,
                AchievementGeneration.is_deleted.is_(False),
            )
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


class AchievementItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_bulk(
        self,
        generation_id: int,
        items: list[dict],
    ) -> list[AchievementGenerationItem]:
        created = []
        for idx, item_data in enumerate(items):
            item = AchievementGenerationItem(
                generation_id=generation_id,
                work_experience_id=item_data.get("work_experience_id"),
                company_name=item_data["company_name"],
                user_achievements_input=item_data.get("user_achievements_input"),
                user_responsibilities_input=item_data.get("user_responsibilities_input"),
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
