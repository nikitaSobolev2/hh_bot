"""Repository for vacancy summary models."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.vacancy_summary import VacancySummary

_PAGE_SIZE = 5


class VacancySummaryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
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

    async def get_by_id(self, summary_id: int) -> VacancySummary | None:
        result = await self._session.execute(
            select(VacancySummary).where(VacancySummary.id == summary_id)
        )
        return result.scalar_one_or_none()

    async def get_by_user_paginated(
        self,
        user_id: int,
        page: int = 0,
    ) -> tuple[list[VacancySummary], int]:
        count_result = await self._session.execute(
            select(VacancySummary).where(
                VacancySummary.user_id == user_id,
                VacancySummary.is_deleted.is_(False),
            )
        )
        total = len(count_result.scalars().all())

        result = await self._session.execute(
            select(VacancySummary)
            .where(
                VacancySummary.user_id == user_id,
                VacancySummary.is_deleted.is_(False),
            )
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
