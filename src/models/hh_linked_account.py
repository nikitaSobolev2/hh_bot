from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.user import User


class HhLinkedAccount(Base):
    """HeadHunter OAuth-linked account for a Telegram user."""

    __tablename__ = "hh_linked_accounts"
    __table_args__ = (UniqueConstraint("user_id", "hh_user_id", name="uq_hh_linked_user_hh_user"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    hh_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), default=None)
    access_token_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    refresh_token_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    access_expires_at: Mapped[datetime | None] = mapped_column(default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)
    last_used_at: Mapped[datetime | None] = mapped_column(default=None)
    browser_storage_enc: Mapped[bytes | None] = mapped_column(LargeBinary, default=None)
    browser_storage_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=None
    )
    resume_list_cache: Mapped[list | None] = mapped_column(JSONB, default=None)
    resume_list_cached_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=None
    )

    user: Mapped[User] = relationship(back_populates="hh_linked_accounts")
