"""Typed schemas for vacancy data flowing through the scraper/extractor pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VacancyApiContext:
    """Structured vacancy context for AI prompts. Built from normalized ORM fields."""

    snippet_requirement: str | None = None
    snippet_responsibility: str | None = None
    key_skills: list[str] = field(default_factory=list)
    experience_name: str | None = None
    schedule_name: str | None = None
    employment_name: str | None = None
    work_format_names: list[str] = field(default_factory=list)
    employer_name: str | None = None


@dataclass(frozen=True)
class VacancyData:
    """A single vacancy scraped from HH.ru."""

    hh_vacancy_id: str
    url: str
    title: str
    raw_skills: list[str] = field(default_factory=list)
    description: str = ""
    ai_keywords: list[str] = field(default_factory=list)
    salary: str = ""
    company_name: str = ""
    work_experience: str = ""
    employment_type: str = ""
    work_schedule: str = ""
    work_formats: str = ""
    compensation_frequency: str = ""
    working_hours: str = ""
    vacancy_api_context: VacancyApiContext | None = None
    employer_data: dict = field(default_factory=dict)
    area_data: dict = field(default_factory=dict)
    orm_fields: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PipelineResult:
    """Aggregated result of a full parsing pipeline run."""

    vacancies: list[VacancyData]
    keywords: list[tuple[str, int]]
    skills: list[tuple[str, int]]

    @property
    def vacancy_count(self) -> int:
        return len(self.vacancies)

    @property
    def keyword_count(self) -> int:
        return len(self.keywords)

    @property
    def skill_count(self) -> int:
        return len(self.skills)


def build_vacancy_api_context(
    orm_fields: dict,
    employer_data: dict,
    raw_skills: list[str] | None = None,
) -> VacancyApiContext:
    """Build VacancyApiContext from mapper output for AI prompts."""
    work_format = orm_fields.get("work_format") or []
    work_format_names = [
        w["name"] for w in work_format if isinstance(w, dict) and w.get("name")
    ]
    return VacancyApiContext(
        snippet_requirement=orm_fields.get("snippet_requirement"),
        snippet_responsibility=orm_fields.get("snippet_responsibility"),
        key_skills=raw_skills or [],
        experience_name=orm_fields.get("experience_name"),
        schedule_name=orm_fields.get("schedule_name"),
        employment_name=orm_fields.get("employment_name"),
        work_format_names=work_format_names,
        employer_name=employer_data.get("name") if employer_data else None,
    )


def build_vacancy_api_context_from_orm(orm) -> VacancyApiContext:
    """Build VacancyApiContext from ParsedVacancy or AutoparsedVacancy ORM."""
    work_format = orm.work_format or []
    work_format_names = [
        w["name"] for w in work_format if isinstance(w, dict) and w.get("name")
    ]
    employer_name = None
    if orm.employer is not None:
        employer_name = orm.employer.name
    return VacancyApiContext(
        snippet_requirement=orm.snippet_requirement,
        snippet_responsibility=orm.snippet_responsibility,
        key_skills=orm.raw_skills or [],
        experience_name=orm.experience_name,
        schedule_name=orm.schedule_name,
        employment_name=orm.employment_name,
        work_format_names=work_format_names,
        employer_name=employer_name,
    )
