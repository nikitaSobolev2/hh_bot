"""HeadHunter.ru UI automation (Playwright) — apply and resume list without applicant API."""

from __future__ import annotations

from typing import Any

from src.services.hh_ui.outcomes import ApplyOutcome, ApplyResult, ListResumesResult, ResumeOption

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

_LAZY_RUNNER = (
    "apply_to_vacancy_ui",
    "list_resumes_ui",
    "normalize_hh_vacancy_url",
    "vacancy_url_from_hh_id",
)


def __getattr__(name: str) -> Any:
    if name in _LAZY_RUNNER:
        from src.services.hh_ui import runner

        return getattr(runner, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
