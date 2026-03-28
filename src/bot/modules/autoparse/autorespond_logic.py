"""Pure helpers for autorespond vacancy selection (unit-tested)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.services.parser.keyword_match import matches_keyword_expression

if TYPE_CHECKING:
    from src.models.autoparse import AutoparsedVacancy


AUTORESPOND_KEYWORD_TITLE_ONLY = "title_only"
AUTORESPOND_KEYWORD_TITLE_AND_KEYWORDS = "title_and_keywords"

AUTORESPOND_MAX_VALID = frozenset({10, 20, 30, 50, -1})


def vacancy_passes_compatibility(
    vacancy: AutoparsedVacancy,
    min_compat: int,
    *,
    allow_missing_score: bool = False,
) -> bool:
    if vacancy.compatibility_score is None:
        return allow_missing_score
    return float(vacancy.compatibility_score) >= float(min_compat)


def vacancy_passes_keyword_mode(
    vacancy: AutoparsedVacancy,
    company_keyword_filter: str,
    mode: str,
) -> bool:
    """Apply company keyword_filter expression (same syntax as parsing); empty passes all."""
    expr = (company_keyword_filter or "").strip()
    if not expr:
        return True
    title = vacancy.title or ""
    if mode == AUTORESPOND_KEYWORD_TITLE_ONLY:
        return matches_keyword_expression(title, expr)
    desc = vacancy.description or ""
    combined = f"{title} {desc}"
    return matches_keyword_expression(combined, expr)


def filter_vacancies_for_autorespond(
    vacancies: list[AutoparsedVacancy],
    *,
    min_compat: int,
    company_keyword_filter: str,
    keyword_mode: str,
    allow_missing_compatibility_score: bool = False,
) -> list[AutoparsedVacancy]:
    """When *allow_missing_compatibility_score* is True, vacancies with no compatibility
    score still pass the compatibility gate (used for explicit ``vacancy_ids`` runs where
    rows may not be scored yet).
    """
    out: list[AutoparsedVacancy] = []
    for v in vacancies:
        if not vacancy_passes_compatibility(
            v,
            min_compat,
            allow_missing_score=allow_missing_compatibility_score,
        ):
            continue
        if not vacancy_passes_keyword_mode(v, company_keyword_filter, keyword_mode):
            continue
        out.append(v)
    return out


def apply_max_cap(vacancies: list[AutoparsedVacancy], max_per_run: int) -> list[AutoparsedVacancy]:
    if max_per_run < 0:
        return vacancies
    return vacancies[:max_per_run]


def work_units_for_autorespond_progress(
    capped: list[AutoparsedVacancy],
    already_handled: set[str],
) -> tuple[int, int]:
    """How many capped rows get a progress tick vs pre-skipped (already applied / employer questions).

    Returns ``(work_units, pre_skipped_autorespond)``. Must match the autorespond loop
    branch that continues without ticking.
    """
    pre_skipped = sum(
        1
        for v in capped
        if v.hh_vacancy_id in already_handled or v.needs_employer_questions
    )
    return len(capped) - pre_skipped, pre_skipped
