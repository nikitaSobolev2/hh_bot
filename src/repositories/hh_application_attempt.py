from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.hh_application_attempt import HhApplicationAttempt
from src.repositories.base import BaseRepository


class HhApplicationAttemptRepository(BaseRepository[HhApplicationAttempt]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, HhApplicationAttempt)

    async def has_successful_apply(
        self,
        user_id: int,
        hh_vacancy_id: str,
        resume_id: str,
    ) -> bool:
        stmt = (
            select(func.count())
            .select_from(HhApplicationAttempt)
            .where(
                HhApplicationAttempt.user_id == user_id,
                HhApplicationAttempt.hh_vacancy_id == hh_vacancy_id,
                HhApplicationAttempt.resume_id == resume_id,
                HhApplicationAttempt.status == "success",
            )
        )
        result = await self._session.execute(stmt)
        return (result.scalar_one() or 0) > 0

    async def hh_vacancy_ids_with_successful_apply(
        self,
        user_id: int,
        resume_id: str,
        hh_vacancy_ids: list[str],
    ) -> set[str]:
        """Return hh_vacancy_id values that already have a successful apply for this user and resume."""
        if not hh_vacancy_ids:
            return set()
        stmt = (
            select(HhApplicationAttempt.hh_vacancy_id)
            .where(
                HhApplicationAttempt.user_id == user_id,
                HhApplicationAttempt.resume_id == resume_id,
                HhApplicationAttempt.hh_vacancy_id.in_(hh_vacancy_ids),
                HhApplicationAttempt.status == "success",
            )
            .distinct()
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return {str(r) for r in rows if r is not None}

    async def hh_vacancy_ids_with_successful_apply_any_resume(
        self,
        user_id: int,
        hh_vacancy_ids: list[str],
    ) -> set[str]:
        """Vacancies the user already responded to successfully (any resume)."""
        if not hh_vacancy_ids:
            return set()
        stmt = (
            select(HhApplicationAttempt.hh_vacancy_id)
            .where(
                HhApplicationAttempt.user_id == user_id,
                HhApplicationAttempt.hh_vacancy_id.in_(hh_vacancy_ids),
                HhApplicationAttempt.status == "success",
            )
            .distinct()
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return {str(r) for r in rows if r is not None}

    async def hh_vacancy_ids_with_success_or_employer_questions(
        self,
        user_id: int,
        hh_vacancy_ids: list[str],
    ) -> set[str]:
        """Vacancies to skip in autorespond: success or employer questions pending (any resume).

        Also skips vacancies where we previously mis-classified HH ``alreadyApplied`` popup JSON
        as ``status=error`` (before ``popup_api:alreadyApplied`` was mapped to ALREADY_RESPONDED).
        """
        if not hh_vacancy_ids:
            return set()
        legacy_already = (
            (HhApplicationAttempt.status == "error")
            & (HhApplicationAttempt.response_excerpt.isnot(None))
            & (HhApplicationAttempt.response_excerpt.contains("popup_api:alreadyApplied"))
        )
        stmt = (
            select(HhApplicationAttempt.hh_vacancy_id)
            .where(
                HhApplicationAttempt.user_id == user_id,
                HhApplicationAttempt.hh_vacancy_id.in_(hh_vacancy_ids),
                or_(
                    HhApplicationAttempt.status.in_(("success", "needs_employer_questions")),
                    legacy_already,
                ),
            )
            .distinct()
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return {str(r) for r in rows if r is not None}

    async def latest_attempt_status_for_user_vacancy(
        self,
        user_id: int,
        hh_vacancy_id: str,
    ) -> str | None:
        """Most recent attempt status for this user and HH vacancy id (by attempt id)."""
        stmt = (
            select(HhApplicationAttempt.status)
            .where(
                HhApplicationAttempt.user_id == user_id,
                HhApplicationAttempt.hh_vacancy_id == hh_vacancy_id,
            )
            .order_by(HhApplicationAttempt.id.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def user_has_any_attempt_for_hh_vacancy(
        self,
        user_id: int,
        hh_vacancy_id: str,
    ) -> bool:
        """True if any attempt row exists for this user+vacancy (sync or real apply)."""
        stmt = (
            select(func.count())
            .select_from(HhApplicationAttempt)
            .where(
                HhApplicationAttempt.user_id == user_id,
                HhApplicationAttempt.hh_vacancy_id == hh_vacancy_id,
            )
        )
        result = await self._session.execute(stmt)
        return (result.scalar_one() or 0) > 0

    async def list_for_feed_session_summary(
        self,
        user_id: int,
        vacancy_ids: list[int],
        since: datetime,
    ) -> list[HhApplicationAttempt]:
        """Latest attempt per vacancy (by created_at desc) within feed session scope."""
        if not vacancy_ids:
            return []
        stmt = (
            select(HhApplicationAttempt)
            .where(
                HhApplicationAttempt.user_id == user_id,
                HhApplicationAttempt.autoparsed_vacancy_id.in_(vacancy_ids),
                HhApplicationAttempt.created_at >= since,
            )
            .order_by(HhApplicationAttempt.created_at.desc())
        )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        seen: set[int] = set()
        out: list[HhApplicationAttempt] = []
        for a in rows:
            vid = a.autoparsed_vacancy_id
            if vid is None or vid in seen:
                continue
            seen.add(vid)
            out.append(a)
        return out
