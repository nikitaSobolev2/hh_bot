"""Tests for autoparsed vacancy construction from scrape dicts."""

from src.worker.tasks.autoparse import _build_autoparsed_vacancy


def test_build_autoparsed_vacancy_sets_needs_employer_questions_when_has_test_in_orm():
    vac = {
        "hh_vacancy_id": "99",
        "url": "https://hh.ru/vacancy/99",
        "title": "Role",
        "orm_fields": {"has_test": True},
    }
    row = _build_autoparsed_vacancy(vac, company_id=1, compat_score=None)
    assert row.needs_employer_questions is True


def test_build_autoparsed_vacancy_clears_needs_employer_questions_without_has_test():
    vac = {
        "hh_vacancy_id": "100",
        "url": "https://hh.ru/vacancy/100",
        "title": "Role",
        "orm_fields": {},
    }
    row = _build_autoparsed_vacancy(vac, company_id=1, compat_score=None)
    assert row.needs_employer_questions is False
