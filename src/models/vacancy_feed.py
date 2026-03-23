from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.autoparse import AutoparseCompany
    from src.models.hh_linked_account import HhLinkedAccount
    from src.models.user import User


class VacancyFeedSession(Base):
    __tablename__ = "vacancy_feed_sessions"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    autoparse_company_id: Mapped[int] = mapped_column(
        ForeignKey("autoparse_companies.id", ondelete="CASCADE"), nullable=False
    )
    hh_linked_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("hh_linked_accounts.id", ondelete="SET NULL"), nullable=True
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    vacancy_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    current_index: Mapped[int] = mapped_column(Integer, default=0)
    liked_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    disliked_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)

    user: Mapped[User] = relationship()
    autoparse_company: Mapped[AutoparseCompany] = relationship()
    hh_linked_account: Mapped[HhLinkedAccount | None] = relationship()

    def __repr__(self) -> str:
        return (
            f"<VacancyFeedSession id={self.id} user={self.user_id} "
            f"index={self.current_index}/{len(self.vacancy_ids)} completed={self.is_completed}>"
        )
