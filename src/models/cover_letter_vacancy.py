"""CoverLetterVacancy model for standalone cover letter generation from main menu."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.user import User


class CoverLetterVacancy(Base):
    """Standalone vacancy for cover letter generation (not tied to autoparse)."""

    __tablename__ = "cover_letter_vacancies"
    __table_args__ = (
        UniqueConstraint("user_id", "hh_vacancy_id", name="uq_cover_letter_user_vacancy"),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    hh_vacancy_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    raw_skills: Mapped[list | None] = mapped_column(JSONB, default=None)

    user: Mapped[User] = relationship(back_populates="cover_letter_vacancies")

    def __repr__(self) -> str:
        return f"<CoverLetterVacancy id={self.id} hh={self.hh_vacancy_id} title={self.title!r}>"
