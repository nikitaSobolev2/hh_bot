"""Map HH.ru API vacancy responses to ORM fields. Handles both list and detail shapes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _safe_str(val: Any, default: str = "") -> str:
    return str(val) if val is not None else default


def _parse_published_at(val: str | None) -> datetime | None:
    """Parse ISO datetime from HH API. Returns naive UTC for DB storage (TIMESTAMP WITHOUT TIME ZONE)."""
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        return None


def _extract_salary_field(
    api_response: dict,
    field: str,
) -> int | str | bool | None:
    """Extract salary field from salary or salary_range."""
    salary = api_response.get("salary") or api_response.get("salary_range")
    if not salary or not isinstance(salary, dict):
        return None
    return salary.get(field)


def map_api_vacancy_to_orm_fields(api_response: dict) -> dict[str, Any]:
    """Map HH API vacancy (list or detail) to ORM field dict.

    Handles both shapes:
    - List: has snippet, no key_skills, no description
    - Detail: has key_skills, description, no snippet

    Returns dict with:
    - employer_data: for HHEmployerRepository.get_or_create_by_hh_id
    - area_data: for HHAreaRepository.get_or_create_by_hh_id
    - orm_fields: flat dict for ParsedVacancy/AutoparsedVacancy assignment
    """
    employer = api_response.get("employer") or {}
    area = api_response.get("area") or {}
    address = api_response.get("address") or {}
    snippet = api_response.get("snippet") or {}
    experience = api_response.get("experience") or {}
    schedule = api_response.get("schedule") or {}
    employment = api_response.get("employment") or {}
    employment_form = api_response.get("employment_form") or {}
    vacancy_type = api_response.get("type") or {}

    employer_data: dict[str, Any] = {}
    if employer and employer.get("id") is not None:
        employer_data = {
            "id": str(employer["id"]),
            "name": employer.get("name", ""),
            "url": employer.get("url"),
            "alternate_url": employer.get("alternate_url"),
            "logo_urls": employer.get("logo_urls"),
            "vacancies_url": employer.get("vacancies_url"),
            "accredited_it_employer": employer.get("accredited_it_employer", False),
            "trusted": employer.get("trusted", False),
            "is_identified_by_esia": employer.get("is_identified_by_esia"),
        }

    area_data: dict[str, Any] = {}
    if area and area.get("id") is not None:
        area_data = {
            "id": str(area["id"]),
            "name": area.get("name", ""),
            "url": area.get("url"),
        }

    salary_from = _extract_salary_field(api_response, "from")
    salary_to = _extract_salary_field(api_response, "to")
    salary_currency = _extract_salary_field(api_response, "currency")
    salary_gross = _extract_salary_field(api_response, "gross")

    orm_fields: dict[str, Any] = {
        "snippet_requirement": snippet.get("requirement") if snippet else None,
        "snippet_responsibility": snippet.get("responsibility") if snippet else None,
        "experience_id": experience.get("id") if isinstance(experience, dict) else None,
        "experience_name": experience.get("name") if isinstance(experience, dict) else None,
        "schedule_id": schedule.get("id") if isinstance(schedule, dict) else None,
        "schedule_name": schedule.get("name") if isinstance(schedule, dict) else None,
        "employment_id": employment.get("id") if isinstance(employment, dict) else None,
        "employment_name": employment.get("name") if isinstance(employment, dict) else None,
        "employment_form_id": employment_form.get("id") if isinstance(employment_form, dict) else None,
        "employment_form_name": employment_form.get("name") if isinstance(employment_form, dict) else None,
        "salary_from": int(salary_from) if salary_from is not None else None,
        "salary_to": int(salary_to) if salary_to is not None else None,
        "salary_currency": str(salary_currency) if salary_currency is not None else None,
        "salary_gross": bool(salary_gross) if salary_gross is not None else None,
        "address_raw": address.get("raw") if isinstance(address, dict) else None,
        "address_city": address.get("city") if isinstance(address, dict) else None,
        "address_street": address.get("street") if isinstance(address, dict) else None,
        "address_building": address.get("building") if isinstance(address, dict) else None,
        "address_lat": float(address["lat"]) if isinstance(address, dict) and address.get("lat") is not None else None,
        "address_lng": float(address["lng"]) if isinstance(address, dict) and address.get("lng") is not None else None,
        "metro_stations": address.get("metro_stations") if isinstance(address, dict) else None,
        "vacancy_type_id": vacancy_type.get("id") if isinstance(vacancy_type, dict) else None,
        "published_at": _parse_published_at(api_response.get("published_at")),
        "work_format": api_response.get("work_format") or None,
        "professional_roles": api_response.get("professional_roles") or None,
    }

    return {
        "employer_data": employer_data,
        "area_data": area_data,
        "orm_fields": orm_fields,
    }
