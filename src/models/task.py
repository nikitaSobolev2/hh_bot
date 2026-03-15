from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.parsing import ParsedVacancy, ParsingCompany
    from src.models.user import User


class BaseCeleryTask(Base):
    """Abstract base for all Celery task tracking records.

    Uses joined-table inheritance so each concrete task type
    gets its own table with task-specific columns while sharing
    common tracking fields in the base table.
    """

    __tablename__ = "celery_tasks"

    celery_task_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    result_data: Mapped[dict | None] = mapped_column(JSONB, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User | None] = relationship(foreign_keys=[user_id])

    __mapper_args__ = {
        "polymorphic_on": "task_type",
        "polymorphic_identity": "base",
    }

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} id={self.id} "
            f"celery_id={self.celery_task_id} status={self.status}>"
        )


class CompanyParseKeywordsFromDescriptionTask(BaseCeleryTask):
    __tablename__ = "tasks_parse_keywords"

    id: Mapped[int] = mapped_column(
        ForeignKey("celery_tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    parsing_company_id: Mapped[int] = mapped_column(
        ForeignKey("parsing_companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    parsed_vacancy_id: Mapped[int | None] = mapped_column(
        ForeignKey("parsed_vacancies.id", ondelete="SET NULL"),
    )
    extracted_keywords: Mapped[list | None] = mapped_column(JSONB, default=None)

    parsing_company: Mapped[ParsingCompany] = relationship(foreign_keys=[parsing_company_id])
    parsed_vacancy: Mapped[ParsedVacancy | None] = relationship(foreign_keys=[parsed_vacancy_id])

    __mapper_args__ = {"polymorphic_identity": "parse_keywords"}


class CompanyCreateKeyPhrasesTask(BaseCeleryTask):
    __tablename__ = "tasks_create_key_phrases"

    id: Mapped[int] = mapped_column(
        ForeignKey("celery_tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    parsing_company_id: Mapped[int] = mapped_column(
        ForeignKey("parsing_companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    style: Mapped[str | None] = mapped_column(String(100), default=None)
    keyword_count: Mapped[int | None] = mapped_column(Integer, default=None)
    generated_phrases: Mapped[str | None] = mapped_column(Text, default=None)

    parsing_company: Mapped[ParsingCompany] = relationship(foreign_keys=[parsing_company_id])

    __mapper_args__ = {"polymorphic_identity": "create_key_phrases"}


class CompanyParseTask(BaseCeleryTask):
    """Task record for the full parsing run (parse_company)."""

    __tablename__ = "tasks_parse_company"

    id: Mapped[int] = mapped_column(
        ForeignKey("celery_tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    parsing_company_id: Mapped[int] = mapped_column(
        ForeignKey("parsing_companies.id", ondelete="CASCADE"),
        nullable=False,
    )

    parsing_company: Mapped[ParsingCompany] = relationship(foreign_keys=[parsing_company_id])

    __mapper_args__ = {"polymorphic_identity": "parse_company"}


class CoverLetterTask(BaseCeleryTask):
    """Task record for cover letter generation (cover_letter)."""

    __tablename__ = "tasks_cover_letter"

    id: Mapped[int] = mapped_column(
        ForeignKey("celery_tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )

    __mapper_args__ = {"polymorphic_identity": "cover_letter"}
