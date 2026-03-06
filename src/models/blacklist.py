from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.user import User


class VacancyBlacklist(Base):
    __tablename__ = "vacancy_blacklist"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "hh_vacancy_id", "vacancy_title_context",
            name="uq_user_vacancy_context",
        ),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    vacancy_title_context: Mapped[str] = mapped_column(String(500), nullable=False)
    hh_vacancy_id: Mapped[str] = mapped_column(String(50), nullable=False)
    vacancy_url: Mapped[str] = mapped_column(Text, nullable=False)
    vacancy_name: Mapped[str] = mapped_column(String(500), default="")
    blacklisted_until: Mapped[datetime] = mapped_column(nullable=False)

    user: Mapped[User] = relationship(back_populates="blacklist_entries")

    def __repr__(self) -> str:
        return (
            f"<VacancyBlacklist id={self.id} user={self.user_id} "
            f"hh={self.hh_vacancy_id} until={self.blacklisted_until}>"
        )
