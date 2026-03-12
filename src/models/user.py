from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.achievement import AchievementGeneration
    from src.models.autoparse import AutoparseCompany
    from src.models.balance import BalanceTransaction
    from src.models.ban import UserBan
    from src.models.blacklist import VacancyBlacklist
    from src.models.interview import Interview
    from src.models.interview_qa import StandardQuestion
    from src.models.parsing import ParsingCompany
    from src.models.referral import ReferralEvent
    from src.models.role import Role
    from src.models.support import SupportTicket
    from src.models.vacancy_summary import VacancySummary
    from src.models.work_experience import UserWorkExperience


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str] = mapped_column(String(255), default="")
    last_name: Mapped[str | None] = mapped_column(String(255))
    language_code: Mapped[str] = mapped_column(String(10), default="ru")
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    referred_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    referral_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)

    notification_settings: Mapped[dict | None] = mapped_column(JSONB, default=None)
    timezone: Mapped[str] = mapped_column(String(50), default="Europe/Moscow")
    autoparse_settings: Mapped[dict | None] = mapped_column(JSONB, default=None)

    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
    )

    role: Mapped[Role] = relationship(back_populates="users", lazy="selectin")
    referred_by: Mapped[User | None] = relationship(remote_side="User.id")

    parsing_companies: Mapped[list[ParsingCompany]] = relationship(back_populates="user")
    autoparse_companies: Mapped[list[AutoparseCompany]] = relationship(
        back_populates="user",
    )
    blacklist_entries: Mapped[list[VacancyBlacklist]] = relationship(back_populates="user")
    balance_transactions: Mapped[list[BalanceTransaction]] = relationship(back_populates="user")
    referral_events: Mapped[list[ReferralEvent]] = relationship(
        back_populates="referrer",
        foreign_keys="ReferralEvent.referrer_id",
    )
    work_experiences: Mapped[list[UserWorkExperience]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    support_tickets: Mapped[list[SupportTicket]] = relationship(
        foreign_keys="SupportTicket.user_id",
        overlaps="user",
    )
    bans: Mapped[list[UserBan]] = relationship(
        foreign_keys="UserBan.user_id",
        overlaps="user",
    )
    interviews: Mapped[list[Interview]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    achievement_generations: Mapped[list[AchievementGeneration]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    standard_questions: Mapped[list[StandardQuestion]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    vacancy_summaries: Mapped[list[VacancySummary]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    @property
    def is_admin(self) -> bool:
        from src.config import settings

        return self.role.name == "admin" or self.telegram_id in settings.admin_ids

    def has_permission(self, permission: str) -> bool:
        return self.role.has_permission(permission)

    def __repr__(self) -> str:
        return f"<User id={self.id} tg={self.telegram_id} name={self.username!r}>"
