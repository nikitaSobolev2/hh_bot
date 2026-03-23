"""HeadHunter.ru UI automation (Playwright) — apply and resume list without applicant API."""

from src.services.hh_ui.outcomes import ApplyOutcome, ApplyResult, ListResumesResult, ResumeOption
from src.services.hh_ui.runner import (
    apply_to_vacancy_ui,
    list_resumes_ui,
    normalize_hh_vacancy_url,
    vacancy_url_from_hh_id,
)

__all__ = [
    "ApplyOutcome",
    "ApplyResult",
    "ListResumesResult",
    "ResumeOption",
    "apply_to_vacancy_ui",
    "list_resumes_ui",
    "normalize_hh_vacancy_url",
    "vacancy_url_from_hh_id",
]
