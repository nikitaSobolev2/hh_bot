"""Vacancy summary (about-me text) model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.user import User


class VacancySummary(Base):
    __tablename__ = "vacancy_summaries"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    generated_text: Mapped[str | None] = mapped_column(Text, default=None)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    # Generation params stored so regenerate can reuse them without re-asking
    excluded_industries: Mapped[str | None] = mapped_column(Text, default=None)
    location: Mapped[str | None] = mapped_column(Text, default=None)
    remote_preference: Mapped[str | None] = mapped_column(Text, default=None)
    additional_notes: Mapped[str | None] = mapped_column(Text, default=None)

    user: Mapped[User] = relationship(back_populates="vacancy_summaries")

    def __repr__(self) -> str:
        return f"<VacancySummary id={self.id} user_id={self.user_id}>"
