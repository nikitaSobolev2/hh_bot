"""Typed schemas for vacancy data flowing through the scraper/extractor pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


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
    raw_api_data: dict = field(default_factory=dict)


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
