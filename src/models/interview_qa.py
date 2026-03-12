"""Standard interview Q&A models."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.user import User


class QuestionCategory:
    BASE = "base"
    AI_GENERATED = "ai_generated"


BASE_QUESTION_KEYS = [
    "why_new_job",
    "best_achievement",
    "worst_achievement",
    "biggest_challenge",
    "five_year_plan",
    "team_conflict",
    "learning_new_tech",
]

WHY_NEW_JOB_REASONS = ["salary", "bored", "relationship", "growth", "relocation", "other"]


class StandardQuestion(Base):
    __tablename__ = "standard_questions"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_key: Mapped[str] = mapped_column(String(100), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[str] = mapped_column(String(20), default=QuestionCategory.AI_GENERATED)
    is_base_question: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[User] = relationship(back_populates="standard_questions")

    def __repr__(self) -> str:
        return f"<StandardQuestion id={self.id} key={self.question_key!r} category={self.category}>"
