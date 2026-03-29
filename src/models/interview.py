"""Interview tracking models."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
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
    company_review: Mapped[str | None] = mapped_column(Text, default=None)
    questions_to_ask: Mapped[str | None] = mapped_column(Text, default=None)
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
    preparation_steps: Mapped[list[InterviewPreparationStep]] = relationship(
        back_populates="interview",
        cascade="all, delete-orphan",
        order_by="InterviewPreparationStep.step_number",
    )
    notes: Mapped[list[InterviewNote]] = relationship(
        back_populates="interview",
        cascade="all, delete-orphan",
        order_by="InterviewNote.sort_order",
    )
    employer_questions: Mapped[list["InterviewEmployerQuestion"]] = relationship(
        back_populates="interview",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Interview id={self.id} title={self.vacancy_title!r}>"


class InterviewNote(Base):
    __tablename__ = "interview_notes"

    interview_id: Mapped[int] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    interview: Mapped[Interview] = relationship(back_populates="notes")

    def __repr__(self) -> str:
        return f"<InterviewNote id={self.id} interview_id={self.interview_id}>"


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


class InterviewEmployerQuestion(Base):
    """Employer-written question and AI-drafted answer for this interview (not prep Q&A)."""

    __tablename__ = "interview_employer_questions"

    interview_id: Mapped[int] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)

    interview: Mapped[Interview] = relationship(back_populates="employer_questions")

    def __repr__(self) -> str:
        return f"<InterviewEmployerQuestion id={self.id} interview_id={self.interview_id}>"


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


class PrepStepStatus:
    PENDING = "pending"
    SKIPPED = "skipped"
    COMPLETED = "completed"


class InterviewPreparationStep(Base):
    __tablename__ = "interview_preparation_steps"

    interview_id: Mapped[int] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_number: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=PrepStepStatus.PENDING)
    deep_summary: Mapped[str | None] = mapped_column(Text, default=None)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    interview: Mapped[Interview] = relationship(back_populates="preparation_steps")
    test: Mapped[InterviewPreparationTest | None] = relationship(
        back_populates="step", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<InterviewPreparationStep id={self.id} step={self.step_number} status={self.status}>"
        )


class InterviewPreparationTest(Base):
    __tablename__ = "interview_preparation_tests"

    step_id: Mapped[int] = mapped_column(
        ForeignKey("interview_preparation_steps.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    questions_json: Mapped[dict | None] = mapped_column(JSONB, default=None)
    user_answers_json: Mapped[dict | None] = mapped_column(JSONB, default=None)

    step: Mapped[InterviewPreparationStep] = relationship(back_populates="test")

    def __repr__(self) -> str:
        return f"<InterviewPreparationTest id={self.id} step_id={self.step_id}>"
