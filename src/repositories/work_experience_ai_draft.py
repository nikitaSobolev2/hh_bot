"""Repository for the work-experience AI draft table."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.work_experience_ai_draft import UserWorkExperienceAiDraft


class WorkExperienceAiDraftRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, user_id: int, field: str, text: str) -> UserWorkExperienceAiDraft:
        """Insert or replace the draft for (user_id, field)."""
        stmt = (
            insert(UserWorkExperienceAiDraft)
            .values(user_id=user_id, field=field, generated_text=text)
            .on_conflict_do_update(
                constraint="uq_we_ai_draft_user_field",
                set_={"generated_text": text},
            )
            .returning(UserWorkExperienceAiDraft)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def get(self, user_id: int, field: str) -> UserWorkExperienceAiDraft | None:
        stmt = select(UserWorkExperienceAiDraft).where(
            UserWorkExperienceAiDraft.user_id == user_id,
            UserWorkExperienceAiDraft.field == field,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(self, user_id: int, field: str) -> None:
        stmt = delete(UserWorkExperienceAiDraft).where(
            UserWorkExperienceAiDraft.user_id == user_id,
            UserWorkExperienceAiDraft.field == field,
        )
        await self._session.execute(stmt)
