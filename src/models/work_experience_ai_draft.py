"""Temporary storage for AI-generated work experience text during creation FSM."""

from __future__ import annotations

from sqlalchemy import Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class UserWorkExperienceAiDraft(Base):
    """Holds AI-generated achievements or duties between the Celery task and the
    "Accept" callback handler.

    The Celery worker has no access to the aiogram FSM, so it stores the result
    here.  The bot handler reads it and writes the accepted text into FSM state
    before continuing the creation flow.  The row is deleted on accept or skip.
    """

    __tablename__ = "user_work_experience_ai_drafts"
    __table_args__ = (UniqueConstraint("user_id", "field", name="uq_we_ai_draft_user_field"),)

    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    field: Mapped[str] = mapped_column(String(50), nullable=False)
    generated_text: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<UserWorkExperienceAiDraft user_id={self.user_id} field={self.field!r}>"
