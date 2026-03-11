"""Interview tracking models."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.user import User


class ExperienceLevel:
    NO_EXPERIENCE = "no_experience"
    JUNIOR = "1-3"
    MIDDLE = "3-6"
    SENIOR = "6+"
    OTHER = "other"

    ALL = [NO_EXPERIENCE, JUNIOR, MIDDLE, SENIOR, OTHER]


class ImprovementStatus:
    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"


class Interview(Base):
    __tablename__ = "interviews"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vacancy_title: Mapped[str] = mapped_column(String(500), nullable=False)
    vacancy_description: Mapped[str | None] = mapped_column(Text, default=None)
    company_name: Mapped[str | None] = mapped_column(String(500), default=None)
    experience_level: Mapped[str | None] = mapped_column(String(50), default=None)
    hh_vacancy_url: Mapped[str | None] = mapped_column(Text, default=None)
    ai_summary: Mapped[str | None] = mapped_column(Text, default=None)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[User] = relationship(back_populates="interviews")
    questions: Mapped[list[InterviewQuestion]] = relationship(
        back_populates="interview",
        cascade="all, delete-orphan",
        order_by="InterviewQuestion.sort_order",
    )
    improvements: Mapped[list[InterviewImprovement]] = relationship(
        back_populates="interview",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Interview id={self.id} title={self.vacancy_title!r}>"


class InterviewQuestion(Base):
    __tablename__ = "interview_questions"

    interview_id: Mapped[int] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    user_answer: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    interview: Mapped[Interview] = relationship(back_populates="questions")

    def __repr__(self) -> str:
        return f"<InterviewQuestion id={self.id} interview_id={self.interview_id}>"


class InterviewImprovement(Base):
    __tablename__ = "interview_improvements"

    interview_id: Mapped[int] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    technology_title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=ImprovementStatus.PENDING)
    improvement_flow: Mapped[str | None] = mapped_column(Text, default=None)

    interview: Mapped[Interview] = relationship(back_populates="improvements")

    def __repr__(self) -> str:
        return (
            f"<InterviewImprovement id={self.id} "
            f"tech={self.technology_title!r} status={self.status}>"
        )
