from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.user import User


class BalanceTransaction(Base):
    __tablename__ = "balance_transactions"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    reference_id: Mapped[str | None] = mapped_column(String(255), default=None)

    user: Mapped[User] = relationship(back_populates="balance_transactions")

    def __repr__(self) -> str:
        return (
            f"<BalanceTransaction id={self.id} user={self.user_id} "
            f"type={self.transaction_type} amount={self.amount}>"
        )
