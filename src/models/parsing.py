from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.user import User


class ParsingCompany(Base):
    __tablename__ = "parsing_companies"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    vacancy_title: Mapped[str] = mapped_column(String(500), nullable=False)
    search_url: Mapped[str] = mapped_column(Text, nullable=False)
    keyword_filter: Mapped[str] = mapped_column(String(500), default="")
    target_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    vacancies_processed: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)
    use_compatibility_check: Mapped[bool] = mapped_column(Boolean, default=False)
    compatibility_threshold: Mapped[int | None] = mapped_column(Integer, default=None)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[User] = relationship(back_populates="parsing_companies")
    vacancies: Mapped[list[ParsedVacancy]] = relationship(
        back_populates="parsing_company",
        cascade="all, delete-orphan",
    )
    aggregated_result: Mapped[AggregatedResult | None] = relationship(
        back_populates="parsing_company",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ParsingCompany id={self.id} title={self.vacancy_title!r} status={self.status}>"


class ParsedVacancy(Base):
    __tablename__ = "parsed_vacancies"

    parsing_company_id: Mapped[int] = mapped_column(
        ForeignKey("parsing_companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    hh_vacancy_id: Mapped[str] = mapped_column(String(50), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    raw_skills: Mapped[list | None] = mapped_column(JSONB, default=None)
    ai_keywords: Mapped[list | None] = mapped_column(JSONB, default=None)
    raw_api_data: Mapped[dict | None] = mapped_column(JSONB, default=None)

    parsing_company: Mapped[ParsingCompany] = relationship(back_populates="vacancies")

    def __repr__(self) -> str:
        return f"<ParsedVacancy id={self.id} hh={self.hh_vacancy_id} title={self.title!r}>"


class AggregatedResult(Base):
    __tablename__ = "aggregated_results"

    parsing_company_id: Mapped[int] = mapped_column(
        ForeignKey("parsing_companies.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    top_keywords: Mapped[dict | None] = mapped_column(JSONB, default=None)
    top_skills: Mapped[dict | None] = mapped_column(JSONB, default=None)
    key_phrases: Mapped[str | None] = mapped_column(Text, default=None)
    key_phrases_style: Mapped[str | None] = mapped_column(String(100), default=None)

    parsing_company: Mapped[ParsingCompany] = relationship(back_populates="aggregated_result")

    def __repr__(self) -> str:
        return f"<AggregatedResult id={self.id} company={self.parsing_company_id}>"
