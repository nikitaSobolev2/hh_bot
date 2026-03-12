"""RecommendationLetter model — one letter per job per resume."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.resume import Resume
    from src.models.work_experience import UserWorkExperience


class RecommendationLetter(Base):
    __tablename__ = "recommendation_letters"

    resume_id: Mapped[int] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_experience_id: Mapped[int] = mapped_column(
        ForeignKey("user_work_experiences.id", ondelete="CASCADE"), nullable=False
    )

    speaker_name: Mapped[str] = mapped_column(String(255), nullable=False)
    speaker_position: Mapped[str | None] = mapped_column(String(255), default=None)

    # One of the predefined character keys, e.g. "professionalism", "leadership", etc.
    character: Mapped[str] = mapped_column(String(100), nullable=False)

    focus_text: Mapped[str | None] = mapped_column(Text, default=None)
    generated_text: Mapped[str | None] = mapped_column(Text, default=None)

    resume: Mapped[Resume] = relationship(back_populates="recommendation_letters")
    work_experience: Mapped[UserWorkExperience] = relationship()

    def __repr__(self) -> str:
        return (
            f"<RecommendationLetter id={self.id} resume_id={self.resume_id} "
            f"work_exp_id={self.work_experience_id}>"
        )
