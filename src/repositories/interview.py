"""Repositories for Interview, InterviewQuestion, and InterviewImprovement."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.interview import Interview, InterviewImprovement, InterviewQuestion
from src.repositories.base import BaseRepository

_PAGE_SIZE = 5


class InterviewRepository(BaseRepository[Interview]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Interview)

    async def get_by_user_paginated(
        self,
        user_id: int,
        page: int = 0,
        page_size: int = _PAGE_SIZE,
    ) -> Sequence[Interview]:
        stmt = (
            select(Interview)
            .where(Interview.user_id == user_id, Interview.is_deleted.is_(False))
            .order_by(Interview.created_at.desc())
            .offset(page * page_size)
            .limit(page_size)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def count_by_user(self, user_id: int) -> int:
        from sqlalchemy import func

        stmt = (
            select(func.count())
            .select_from(Interview)
            .where(
                Interview.user_id == user_id,
                Interview.is_deleted.is_(False),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def get_with_relations(self, interview_id: int) -> Interview | None:
        stmt = (
            select(Interview)
            .where(Interview.id == interview_id)
            .options(
                selectinload(Interview.questions),
                selectinload(Interview.improvements),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def soft_delete(self, interview_id: int) -> None:
        interview = await self.get_by_id(interview_id)
        if interview:
            await self.update(interview, is_deleted=True)


class InterviewQuestionRepository(BaseRepository[InterviewQuestion]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, InterviewQuestion)

    async def get_by_interview(self, interview_id: int) -> Sequence[InterviewQuestion]:
        stmt = (
            select(InterviewQuestion)
            .where(InterviewQuestion.interview_id == interview_id)
            .order_by(InterviewQuestion.sort_order)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def bulk_create(
        self,
        interview_id: int,
        questions: list[dict[str, str]],
    ) -> list[InterviewQuestion]:
        created = []
        for idx, qa in enumerate(questions):
            instance = InterviewQuestion(
                interview_id=interview_id,
                question=qa["question"],
                user_answer=qa["answer"],
                sort_order=idx,
            )
            self._session.add(instance)
            created.append(instance)
        await self._session.flush()
        return created


class InterviewImprovementRepository(BaseRepository[InterviewImprovement]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, InterviewImprovement)

    async def get_by_interview(self, interview_id: int) -> Sequence[InterviewImprovement]:
        stmt = (
            select(InterviewImprovement)
            .where(InterviewImprovement.interview_id == interview_id)
            .order_by(InterviewImprovement.created_at)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def update_status(self, improvement_id: int, status: str) -> None:
        improvement = await self.get_by_id(improvement_id)
        if improvement:
            await self.update(improvement, status=status)

    async def set_improvement_flow(self, improvement_id: int, flow: str) -> None:
        improvement = await self.get_by_id(improvement_id)
        if improvement:
            await self.update(improvement, improvement_flow=flow)
