"""Repository for standard interview Q&A models."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.interview_qa import QuestionCategory, StandardQuestion


class StandardQuestionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_all_for_user(self, user_id: int) -> list[StandardQuestion]:
        result = await self._session.execute(
            select(StandardQuestion)
            .where(
                StandardQuestion.user_id == user_id,
                StandardQuestion.is_deleted.is_(False),
            )
            .order_by(StandardQuestion.created_at)
        )
        return list(result.scalars().all())

    async def get_by_key(self, user_id: int, question_key: str) -> StandardQuestion | None:
        result = await self._session.execute(
            select(StandardQuestion).where(
                StandardQuestion.user_id == user_id,
                StandardQuestion.question_key == question_key,
                StandardQuestion.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def upsert_answer(
        self,
        user_id: int,
        question_key: str,
        question_text: str,
        answer_text: str,
        *,
        is_base_question: bool = False,
        category: str = QuestionCategory.AI_GENERATED,
    ) -> StandardQuestion:
        existing = await self.get_by_key(user_id, question_key)
        if existing:
            existing.answer_text = answer_text
            existing.question_text = question_text
            await self._session.flush()
            return existing

        question = StandardQuestion(
            user_id=user_id,
            question_key=question_key,
            question_text=question_text,
            answer_text=answer_text,
            category=category,
            is_base_question=is_base_question,
        )
        self._session.add(question)
        await self._session.flush()
        return question

    async def get_ai_generated(self, user_id: int) -> list[StandardQuestion]:
        result = await self._session.execute(
            select(StandardQuestion)
            .where(
                StandardQuestion.user_id == user_id,
                StandardQuestion.category == QuestionCategory.AI_GENERATED,
                StandardQuestion.is_deleted.is_(False),
            )
            .order_by(StandardQuestion.created_at)
        )
        return list(result.scalars().all())

    async def soft_delete(self, question: StandardQuestion) -> None:
        question.is_deleted = True
        await self._session.flush()
