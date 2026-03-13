"""Repositories for Interview, InterviewQuestion, and InterviewImprovement."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.interview import (
    Interview,
    InterviewImprovement,
    InterviewPreparationStep,
    InterviewPreparationTest,
    InterviewQuestion,
)
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
                selectinload(Interview.preparation_steps),
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
        questions: list[QAPair],  # noqa: F821
    ) -> list[InterviewQuestion]:
        created = []
        for idx, qa in enumerate(questions):
            question_text = qa.question if hasattr(qa, "question") else qa["question"]
            answer_text = qa.answer if hasattr(qa, "answer") else qa["answer"]
            instance = InterviewQuestion(
                interview_id=interview_id,
                question=question_text,
                user_answer=answer_text,
                sort_order=idx,
            )
            self._session.add(instance)
            created.append(instance)
        await self._session.flush()
        return created


class InterviewPreparationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_steps_for_interview(self, interview_id: int) -> list[InterviewPreparationStep]:
        result = await self._session.execute(
            select(InterviewPreparationStep)
            .where(
                InterviewPreparationStep.interview_id == interview_id,
                InterviewPreparationStep.is_deleted.is_(False),
            )
            .order_by(InterviewPreparationStep.step_number)
        )
        return list(result.scalars().all())

    async def get_step_by_id(self, step_id: int) -> InterviewPreparationStep | None:
        from sqlalchemy.orm import joinedload

        result = await self._session.execute(
            select(InterviewPreparationStep)
            .where(InterviewPreparationStep.id == step_id)
            .options(
                joinedload(InterviewPreparationStep.interview),
                joinedload(InterviewPreparationStep.test),
            )
        )
        return result.scalar_one_or_none()

    async def update_step_status(self, step_id: int, status: str) -> None:
        step = await self.get_step_by_id(step_id)
        if step:
            step.status = status
            await self._session.flush()

    async def update_step_deep_summary(self, step_id: int, deep_summary: str) -> None:
        step = await self.get_step_by_id(step_id)
        if step:
            step.deep_summary = deep_summary
            await self._session.flush()

    async def get_test_by_step(self, step_id: int) -> InterviewPreparationTest | None:
        result = await self._session.execute(
            select(InterviewPreparationTest).where(InterviewPreparationTest.step_id == step_id)
        )
        return result.scalar_one_or_none()

    async def save_test_answers(self, step_id: int, answers: dict) -> None:
        test = await self.get_test_by_step(step_id)
        if test:
            test.user_answers_json = answers
            await self._session.flush()


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
