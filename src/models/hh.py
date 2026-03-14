"""HH.ru API reference models: employer and area."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.autoparse import AutoparsedVacancy
    from src.models.parsing import ParsedVacancy


class HHEmployer(Base):
    """Employer from HH.ru API. Many vacancies per employer."""

    __tablename__ = "hh_employers"

    hh_employer_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    alternate_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_urls: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    vacancies_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    accredited_it_employer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trusted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_identified_by_esia: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    parsed_vacancies: Mapped[list[ParsedVacancy]] = relationship(
        "ParsedVacancy",
        back_populates="employer",
        foreign_keys="ParsedVacancy.employer_id",
    )
    autoparsed_vacancies: Mapped[list[AutoparsedVacancy]] = relationship(
        "AutoparsedVacancy",
        back_populates="employer",
        foreign_keys="AutoparsedVacancy.employer_id",
    )

    def __repr__(self) -> str:
        return f"<HHEmployer id={self.id} hh_id={self.hh_employer_id!r} name={self.name!r}>"


class HHArea(Base):
    """Area (region/city) from HH.ru API. Many vacancies per area."""

    __tablename__ = "hh_areas"

    hh_area_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)

    parsed_vacancies: Mapped[list[ParsedVacancy]] = relationship(
        "ParsedVacancy",
        back_populates="area",
        foreign_keys="ParsedVacancy.area_id",
    )
    autoparsed_vacancies: Mapped[list[AutoparsedVacancy]] = relationship(
        "AutoparsedVacancy",
        back_populates="area",
        foreign_keys="AutoparsedVacancy.area_id",
    )

    def __repr__(self) -> str:
        return f"<HHArea id={self.id} hh_id={self.hh_area_id!r} name={self.name!r}>"
