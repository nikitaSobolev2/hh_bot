"""Unit tests for autorespond pinned progress (work units vs pre-skips)."""

from __future__ import annotations

from types import SimpleNamespace

from src.bot.modules.autoparse.autorespond_logic import work_units_for_autorespond_progress


def _vac(*, hh_id: str = "1", needs_eq: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        hh_vacancy_id=hh_id,
        needs_employer_questions=needs_eq,
    )


def test_work_units_all_pre_skipped_by_attempt_set() -> None:
    capped = [_vac(hh_id="a"), _vac(hh_id="b")]
    already = {"a", "b"}
    work, pre = work_units_for_autorespond_progress(capped, already)
    assert work == 0
    assert pre == 2


def test_work_units_none_pre_skipped() -> None:
    capped = [_vac(hh_id="1"), _vac(hh_id="2")]
    work, pre = work_units_for_autorespond_progress(capped, set())
    assert work == 2
    assert pre == 0


def test_work_units_flag_needs_employer_questions_counts_as_pre_skip() -> None:
    capped = [_vac(hh_id="x"), _vac(hh_id="y", needs_eq=True)]
    work, pre = work_units_for_autorespond_progress(capped, set())
    assert work == 1
    assert pre == 1


def test_work_units_mixed() -> None:
    capped = [
        _vac(hh_id="done1"),
        _vac(hh_id="new1"),
        _vac(hh_id="done2"),
        _vac(hh_id="new2"),
    ]
    work, pre = work_units_for_autorespond_progress(capped, {"done1", "done2"})
    assert work == 2
    assert pre == 2


def test_work_units_empty_capped() -> None:
    work, pre = work_units_for_autorespond_progress([], {"1"})
    assert work == 0
    assert pre == 0
