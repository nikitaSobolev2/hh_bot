"""Repository for Resume model."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.resume import Resume

_PAGE_SIZE = 5


class ResumeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: int,
        job_title: str,
        skill_level: str | None = None,
    ) -> Resume:
        resume = Resume(
            user_id=user_id,
            job_title=job_title,
            skill_level=skill_level,
        )
        self._session.add(resume)
        await self._session.flush()
        return resume

    async def get_by_id(self, resume_id: int) -> Resume | None:
        return await self._session.get(Resume, resume_id)

    async def get_latest_by_user(self, user_id: int) -> Resume | None:
        result = await self._session.execute(
            select(Resume)
            .where(Resume.user_id == user_id, Resume.is_deleted.is_(False))
            .order_by(Resume.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_user_paginated(
        self,
        user_id: int,
        page: int = 0,
    ) -> tuple[list[Resume], int]:
        count_result = await self._session.execute(
            select(func.count())
            .select_from(Resume)
            .where(
                Resume.user_id == user_id,
                Resume.is_deleted.is_(False),
            )
        )
        total = count_result.scalar_one()

        result = await self._session.execute(
            select(Resume)
            .where(
                Resume.user_id == user_id,
                Resume.is_deleted.is_(False),
            )
            .order_by(Resume.created_at.desc())
            .offset(page * _PAGE_SIZE)
            .limit(_PAGE_SIZE)
        )
        return list(result.scalars().all()), total

    async def update(self, resume: Resume, **kwargs) -> Resume:
        for key, value in kwargs.items():
            setattr(resume, key, value)
        await self._session.flush()
        return resume

    async def soft_delete(self, resume: Resume) -> None:
        resume.is_deleted = True
        await self._session.flush()
