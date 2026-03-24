"""Pure helpers for autorespond vacancy selection (unit-tested)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.autoparse import AutoparsedVacancy


AUTORESPOND_KEYWORD_TITLE_ONLY = "title_only"
AUTORESPOND_KEYWORD_TITLE_AND_KEYWORDS = "title_and_keywords"

AUTORESPOND_MAX_VALID = frozenset({10, 20, 30, 50, -1})


def _keyword_tokens(keyword_filter: str) -> list[str]:
    return [t.lower() for t in keyword_filter.split() if t.strip()]


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
    """Apply company keyword_filter tokens; empty filter passes all."""
    tokens = _keyword_tokens(company_keyword_filter)
    if not tokens:
        return True
    title = (vacancy.title or "").lower()
    desc = (vacancy.description or "").lower()
    if mode == AUTORESPOND_KEYWORD_TITLE_ONLY:
        return all(t in title for t in tokens)
    if mode == AUTORESPOND_KEYWORD_TITLE_AND_KEYWORDS:
        combined = f"{title} {desc}"
        return all(t in combined for t in tokens)
    combined = f"{title} {desc}"
    return all(t in combined for t in tokens)


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
