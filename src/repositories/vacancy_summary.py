"""Repository for vacancy summary models."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.vacancy_summary import VacancySummary
from src.repositories.base import BaseRepository

_PAGE_SIZE = 5


class VacancySummaryRepository(BaseRepository[VacancySummary]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, VacancySummary)

    async def create_for_user(
        self,
        user_id: int,
        excluded_industries: str | None = None,
        location: str | None = None,
        remote_preference: str | None = None,
        additional_notes: str | None = None,
    ) -> VacancySummary:
        summary = VacancySummary(
            user_id=user_id,
            excluded_industries=excluded_industries,
            location=location,
            remote_preference=remote_preference,
            additional_notes=additional_notes,
        )
        self._session.add(summary)
        await self._session.flush()
        return summary

    async def get_by_user_paginated(
        self,
        user_id: int,
        page: int = 0,
    ) -> tuple[list[VacancySummary], int]:
        base_where = (
            VacancySummary.user_id == user_id,
            VacancySummary.is_deleted.is_(False),
        )

        count_stmt = select(func.count()).select_from(VacancySummary).where(*base_where)
        total = await self._session.scalar(count_stmt) or 0

        result = await self._session.execute(
            select(VacancySummary)
            .where(*base_where)
            .order_by(VacancySummary.created_at.desc())
            .offset(page * _PAGE_SIZE)
            .limit(_PAGE_SIZE)
        )
        return list(result.scalars().all()), total

    async def update_text(self, summary: VacancySummary, text: str) -> None:
        summary.generated_text = text
        await self._session.flush()

    async def soft_delete(self, summary: VacancySummary) -> None:
        summary.is_deleted = True
        await self._session.flush()
