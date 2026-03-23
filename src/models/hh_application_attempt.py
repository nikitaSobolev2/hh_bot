from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.autoparse import AutoparsedVacancy
    from src.models.hh_linked_account import HhLinkedAccount
    from src.models.user import User


class HhApplicationAttempt(Base):
    """Audit log for HH apply / negotiation attempts from the feed."""

    __tablename__ = "hh_application_attempts"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    hh_linked_account_id: Mapped[int] = mapped_column(
        ForeignKey("hh_linked_accounts.id", ondelete="SET NULL"), nullable=True
    )
    autoparsed_vacancy_id: Mapped[int | None] = mapped_column(
        ForeignKey("autoparsed_vacancies.id", ondelete="SET NULL"), nullable=True
    )
    hh_vacancy_id: Mapped[str] = mapped_column(String(50), nullable=False)
    resume_id: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    api_negotiation_id: Mapped[str | None] = mapped_column(String(80), default=None)
    error_code: Mapped[str | None] = mapped_column(String(120), default=None)
    response_excerpt: Mapped[str | None] = mapped_column(Text, default=None)

    user: Mapped[User] = relationship()
    hh_linked_account: Mapped[HhLinkedAccount | None] = relationship()
    autoparsed_vacancy: Mapped[AutoparsedVacancy | None] = relationship()
