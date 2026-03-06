from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.user import User


class ReferralEvent(Base):
    __tablename__ = "referral_events"

    referrer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    referred_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    bonus_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    referrer: Mapped[User] = relationship(
        back_populates="referral_events",
        foreign_keys=[referrer_id],
    )
    referred: Mapped[User] = relationship(foreign_keys=[referred_id])

    def __repr__(self) -> str:
        return (
            f"<ReferralEvent id={self.id} referrer={self.referrer_id} "
            f"referred={self.referred_id} type={self.event_type}>"
        )
