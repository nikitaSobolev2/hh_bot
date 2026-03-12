from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.user import User


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="new")
    close_result: Mapped[str | None] = mapped_column(Text)
    close_status: Mapped[str | None] = mapped_column(String(20))
    channel_message_id: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship(
        foreign_keys=[user_id],
        lazy="selectin",
        overlaps="support_tickets",
    )
    admin: Mapped[User | None] = relationship(
        foreign_keys=[admin_id],
        lazy="selectin",
    )
    messages: Mapped[list[SupportMessage]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
    )
    attachments: Mapped[list[SupportAttachment]] = relationship(
        primaryjoin="and_(SupportAttachment.ticket_id == SupportTicket.id, "
        "SupportAttachment.message_id.is_(None))",
        cascade="all, delete-orphan",
        foreign_keys="SupportAttachment.ticket_id",
    )

    def __repr__(self) -> str:
        return f"<SupportTicket id={self.id} status={self.status!r} user={self.user_id}>"


class SupportMessage(Base):
    __tablename__ = "support_messages"

    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("support_tickets.id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    text: Mapped[str | None] = mapped_column(Text)
    is_from_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_seen: Mapped[bool] = mapped_column(Boolean, default=False)

    ticket: Mapped[SupportTicket] = relationship(back_populates="messages")
    sender: Mapped[User] = relationship(lazy="selectin")
    attachments: Mapped[list[SupportAttachment]] = relationship(
        primaryjoin="SupportAttachment.message_id == SupportMessage.id",
        cascade="all, delete-orphan",
        foreign_keys="SupportAttachment.message_id",
    )

    def __repr__(self) -> str:
        return f"<SupportMessage id={self.id} ticket={self.ticket_id} admin={self.is_from_admin}>"


class SupportAttachment(Base):
    __tablename__ = "support_attachments"

    ticket_id: Mapped[int | None] = mapped_column(
        ForeignKey("support_tickets.id", ondelete="CASCADE"),
    )
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("support_messages.id", ondelete="CASCADE"),
    )
    file_id: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str | None] = mapped_column(String(100))

    def __repr__(self) -> str:
        return f"<SupportAttachment id={self.id} type={self.file_type!r}>"
