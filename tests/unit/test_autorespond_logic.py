"""Unit tests for autorespond vacancy selection helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.bot.modules.autoparse import autorespond_logic as ar


def _vac(
    *,
    compat: float | None = 80.0,
    title: str = "Python Developer",
    description: str = "We need django",
    hh_id: str = "1",
) -> SimpleNamespace:
    return SimpleNamespace(
        compatibility_score=compat,
        title=title,
        description=description,
        hh_vacancy_id=hh_id,
    )


def test_compat_below_threshold_filtered_out() -> None:
    v = _vac(compat=40.0)
    out = ar.filter_vacancies_for_autorespond(
        [v],
        min_compat=50,
        company_keyword_filter="",
        keyword_mode=ar.AUTORESPOND_KEYWORD_TITLE_AND_KEYWORDS,
    )
    assert out == []


def test_compat_none_filtered_out() -> None:
    v = _vac(compat=None)
    out = ar.filter_vacancies_for_autorespond(
        [v],
        min_compat=50,
        company_keyword_filter="",
        keyword_mode=ar.AUTORESPOND_KEYWORD_TITLE_AND_KEYWORDS,
    )
    assert out == []


def test_compat_none_included_when_allow_missing_score() -> None:
    v = _vac(compat=None)
    out = ar.filter_vacancies_for_autorespond(
        [v],
        min_compat=50,
        company_keyword_filter="",
        keyword_mode=ar.AUTORESPOND_KEYWORD_TITLE_AND_KEYWORDS,
        allow_missing_compatibility_score=True,
    )
    assert out == [v]


def test_compat_below_threshold_still_filtered_when_allow_missing() -> None:
    """Explicit-ID mode only relaxes *missing* scores, not low scores."""
    v = _vac(compat=40.0)
    out = ar.filter_vacancies_for_autorespond(
        [v],
        min_compat=50,
        company_keyword_filter="",
        keyword_mode=ar.AUTORESPOND_KEYWORD_TITLE_AND_KEYWORDS,
        allow_missing_compatibility_score=True,
    )
    assert out == []


def test_title_only_requires_tokens_in_title() -> None:
    ok = _vac(title="Senior Python Engineer", description="no django here")
    bad = _vac(
        title="Java Developer",
        description="python django stack",
        hh_id="2",
    )
    out = ar.filter_vacancies_for_autorespond(
        [ok, bad],
        min_compat=50,
        company_keyword_filter="python",
        keyword_mode=ar.AUTORESPOND_KEYWORD_TITLE_ONLY,
    )
    assert len(out) == 1 and out[0].title == "Senior Python Engineer"


def test_title_and_keywords_matches_description() -> None:
    v = _vac(title="Developer", description="Must know Python and Django")
    out = ar.filter_vacancies_for_autorespond(
        [v],
        min_compat=50,
        company_keyword_filter="django",
        keyword_mode=ar.AUTORESPOND_KEYWORD_TITLE_AND_KEYWORDS,
    )
    assert len(out) == 1


def test_empty_keyword_filter_passes() -> None:
    v = _vac(title="X", description="Y", compat=60.0)
    out = ar.filter_vacancies_for_autorespond(
        [v],
        min_compat=50,
        company_keyword_filter="   ",
        keyword_mode=ar.AUTORESPOND_KEYWORD_TITLE_ONLY,
    )
    assert out == [v]


def test_multiple_tokens_all_required() -> None:
    a = _vac(title="Python Django Developer", hh_id="1")
    b = _vac(title="Python only", hh_id="2")
    out = ar.filter_vacancies_for_autorespond(
        [a, b],
        min_compat=50,
        company_keyword_filter="python django",
        keyword_mode=ar.AUTORESPOND_KEYWORD_TITLE_ONLY,
    )
    assert len(out) == 1 and out[0].hh_vacancy_id == "1"


def test_apply_max_cap_negative_means_unlimited() -> None:
    vs = [_vac(hh_id=str(i)) for i in range(5)]
    capped = ar.apply_max_cap(vs, -1)
    assert len(capped) == 5


@pytest.mark.parametrize("n", [10, 20, 30, 50])
def test_apply_max_cap_limits(n: int) -> None:
    vs = [_vac(hh_id=str(i)) for i in range(100)]
    capped = ar.apply_max_cap(vs, n)
    assert len(capped) == n
