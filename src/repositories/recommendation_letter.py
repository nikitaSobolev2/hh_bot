"""Repository for RecommendationLetter model."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.recommendation_letter import RecommendationLetter


class RecommendationLetterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        resume_id: int,
        work_experience_id: int,
        speaker_name: str,
        character: str,
        speaker_position: str | None = None,
        focus_text: str | None = None,
    ) -> RecommendationLetter:
        letter = RecommendationLetter(
            resume_id=resume_id,
            work_experience_id=work_experience_id,
            speaker_name=speaker_name,
            character=character,
            speaker_position=speaker_position,
            focus_text=focus_text,
        )
        self._session.add(letter)
        await self._session.flush()
        return letter

    async def get_by_id(self, letter_id: int) -> RecommendationLetter | None:
        return await self._session.get(RecommendationLetter, letter_id)

    async def get_by_resume(self, resume_id: int) -> list[RecommendationLetter]:
        result = await self._session.execute(
            select(RecommendationLetter)
            .where(RecommendationLetter.resume_id == resume_id)
            .order_by(RecommendationLetter.created_at)
        )
        return list(result.scalars().all())

    async def get_by_resume_and_work_exp(
        self,
        resume_id: int,
        work_experience_id: int,
    ) -> RecommendationLetter | None:
        result = await self._session.execute(
            select(RecommendationLetter).where(
                RecommendationLetter.resume_id == resume_id,
                RecommendationLetter.work_experience_id == work_experience_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_generated_text(self, letter: RecommendationLetter, text: str) -> None:
        letter.generated_text = text
        await self._session.flush()
