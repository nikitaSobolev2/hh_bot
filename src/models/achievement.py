"""Achievement generation models."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.user import User
    from src.models.work_experience import UserWorkExperience


class GenerationStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AchievementGeneration(Base):
    __tablename__ = "achievement_generations"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default=GenerationStatus.PENDING)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[User] = relationship(back_populates="achievement_generations")
    items: Mapped[list[AchievementGenerationItem]] = relationship(
        back_populates="generation",
        cascade="all, delete-orphan",
        order_by="AchievementGenerationItem.id",
    )

    def __repr__(self) -> str:
        return f"<AchievementGeneration id={self.id} status={self.status}>"


class AchievementGenerationItem(Base):
    __tablename__ = "achievement_generation_items"

    generation_id: Mapped[int] = mapped_column(
        ForeignKey("achievement_generations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_experience_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_work_experiences.id", ondelete="SET NULL"), default=None
    )
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    user_achievements_input: Mapped[str | None] = mapped_column(Text, default=None)
    user_responsibilities_input: Mapped[str | None] = mapped_column(Text, default=None)
    generated_text: Mapped[str | None] = mapped_column(Text, default=None)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    generation: Mapped[AchievementGeneration] = relationship(back_populates="items")
    work_experience: Mapped[UserWorkExperience | None] = relationship()

    def __repr__(self) -> str:
        return (
            f"<AchievementGenerationItem id={self.id} "
            f"generation_id={self.generation_id} company={self.company_name!r}>"
        )
