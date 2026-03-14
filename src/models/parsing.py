from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.hh import HHArea, HHEmployer
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

    employer_id: Mapped[int | None] = mapped_column(
        ForeignKey("hh_employers.id", ondelete="SET NULL"), nullable=True
    )
    area_id: Mapped[int | None] = mapped_column(
        ForeignKey("hh_areas.id", ondelete="SET NULL"), nullable=True
    )
    snippet_requirement: Mapped[str | None] = mapped_column(Text, nullable=True)
    snippet_responsibility: Mapped[str | None] = mapped_column(Text, nullable=True)
    experience_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    experience_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    schedule_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    schedule_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    employment_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    employment_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    employment_form_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    employment_form_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    salary_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    salary_gross: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    address_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_city: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address_street: Mapped[str | None] = mapped_column(String(500), nullable=True)
    address_building: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    address_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    metro_stations: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    vacancy_type_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)
    work_format: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    professional_roles: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    parsing_company: Mapped[ParsingCompany] = relationship(back_populates="vacancies")
    employer: Mapped[HHEmployer | None] = relationship(
        back_populates="parsed_vacancies",
        foreign_keys=[employer_id],
    )
    area: Mapped[HHArea | None] = relationship(
        back_populates="parsed_vacancies",
        foreign_keys=[area_id],
    )

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
