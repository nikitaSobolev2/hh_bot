from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.support import SupportTicket
    from src.models.user import User


class UserBan(Base):
    __tablename__ = "user_bans"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    admin_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    banned_until: Mapped[datetime | None] = mapped_column()
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    ticket_id: Mapped[int | None] = mapped_column(
        ForeignKey("support_tickets.id", ondelete="SET NULL"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="selectin", overlaps="bans")
    admin: Mapped[User] = relationship(foreign_keys=[admin_id], lazy="selectin")
    ticket: Mapped[SupportTicket | None] = relationship(lazy="selectin")

    def __repr__(self) -> str:
        return f"<UserBan id={self.id} user={self.user_id} active={self.is_active}>"
