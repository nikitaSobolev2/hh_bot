from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.hh import HHArea, HHEmployer
    from src.models.user import User


class AutoparseCompany(Base):
    __tablename__ = "autoparse_companies"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    vacancy_title: Mapped[str] = mapped_column(String(500), nullable=False)
    search_url: Mapped[str] = mapped_column(Text, nullable=False)
    keyword_filter: Mapped[str] = mapped_column(String(500), default="")
    skills: Mapped[str] = mapped_column(Text, default="")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    last_parsed_at: Mapped[datetime | None] = mapped_column(default=None)
    last_delivered_at: Mapped[datetime | None] = mapped_column(default=None)
    total_runs: Mapped[int] = mapped_column(Integer, default=0)
    total_vacancies_found: Mapped[int] = mapped_column(Integer, default=0)
    include_reacted_in_feed: Mapped[bool] = mapped_column(Boolean, default=False)

    autorespond_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    autorespond_min_compat: Mapped[int] = mapped_column(Integer, default=50)
    autorespond_keyword_mode: Mapped[str] = mapped_column(
        String(32), default="title_and_keywords"
    )
    autorespond_max_per_run: Mapped[int] = mapped_column(Integer, default=20)
    autorespond_resume_id: Mapped[str | None] = mapped_column(String(80), default=None)
    autorespond_hh_linked_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("hh_linked_accounts.id", ondelete="SET NULL"), nullable=True
    )

    user: Mapped[User] = relationship(back_populates="autoparse_companies")
    vacancies: Mapped[list[AutoparsedVacancy]] = relationship(
        back_populates="autoparse_company",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<AutoparseCompany id={self.id} title={self.vacancy_title!r} "
            f"enabled={self.is_enabled}>"
        )


class AutoparsedVacancy(Base):
    __tablename__ = "autoparsed_vacancies"
    __table_args__ = (
        UniqueConstraint(
            "autoparse_company_id", "hh_vacancy_id", name="uq_autoparse_company_vacancy"
        ),
    )

    autoparse_company_id: Mapped[int] = mapped_column(
        ForeignKey("autoparse_companies.id", ondelete="CASCADE"), nullable=False
    )
    hh_vacancy_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    raw_skills: Mapped[list | None] = mapped_column(JSONB, default=None)
    company_name: Mapped[str | None] = mapped_column(String(500))
    company_url: Mapped[str | None] = mapped_column(Text)
    salary: Mapped[str | None] = mapped_column(String(200))
    compensation_frequency: Mapped[str | None] = mapped_column(String(200))
    work_experience: Mapped[str | None] = mapped_column(String(200))
    employment_type: Mapped[str | None] = mapped_column(String(200))
    work_schedule: Mapped[str | None] = mapped_column(String(200))
    working_hours: Mapped[str | None] = mapped_column(String(200))
    work_formats: Mapped[str | None] = mapped_column(String(200))
    tags: Mapped[list | None] = mapped_column(JSONB, default=None)
    compatibility_score: Mapped[float | None] = mapped_column(Float, default=None)
    ai_summary: Mapped[str | None] = mapped_column(Text, default=None)
    ai_stack: Mapped[list | None] = mapped_column(JSONB, default=None)

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
    needs_employer_questions: Mapped[bool] = mapped_column(Boolean, default=False)

    autoparse_company: Mapped[AutoparseCompany] = relationship(back_populates="vacancies")
    employer: Mapped[HHEmployer | None] = relationship(
        back_populates="autoparsed_vacancies",
        foreign_keys=[employer_id],
    )
    area: Mapped[HHArea | None] = relationship(
        back_populates="autoparsed_vacancies",
        foreign_keys=[area_id],
    )

    def __repr__(self) -> str:
        return f"<AutoparsedVacancy id={self.id} hh={self.hh_vacancy_id} title={self.title!r}>"


# Negotiations sync: HH public API returned 404 — we still store a stub row for feed/liked merge.
# This score is excluded from feed delivery and compat-update queries (see AutoparsedVacancyRepository).
NEGOTIATIONS_SYNC_PLACEHOLDER_COMPAT = -1.0
