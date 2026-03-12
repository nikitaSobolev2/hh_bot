"""Resume model — stores a resume generation session result."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.recommendation_letter import RecommendationLetter
    from src.models.user import User
    from src.models.vacancy_summary import VacancySummary


class Resume(Base):
    __tablename__ = "resumes"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_title: Mapped[str] = mapped_column(String(255), nullable=False)
    skill_level: Mapped[str | None] = mapped_column(String(100), default=None)

    # Raw HH.ru parsed keywords dict {keyword: count} captured during the flow
    parsed_keywords: Mapped[dict | None] = mapped_column(JSON, default=None)

    # AI-generated keyphrases grouped by company: {company_name: "- phrase\n- phrase"}
    keyphrases_by_company: Mapped[dict | None] = mapped_column(JSON, default=None)

    # Work experience IDs the user disabled for this session only
    disabled_work_exp_ids: Mapped[list | None] = mapped_column(JSON, default=None)

    # FK to the vacancy summary selected/generated in step 6
    summary_id: Mapped[int | None] = mapped_column(
        ForeignKey("vacancy_summaries.id", ondelete="SET NULL"), default=None
    )

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[User] = relationship(back_populates="resumes")
    summary: Mapped[VacancySummary | None] = relationship()
    recommendation_letters: Mapped[list[RecommendationLetter]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Resume id={self.id} user_id={self.user_id} job_title={self.job_title!r}>"
