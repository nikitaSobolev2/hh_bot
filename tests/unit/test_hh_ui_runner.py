"""Tests for HH UI runner helpers (no real browser)."""

from src.services.hh_ui.runner import normalize_hh_vacancy_url, vacancy_url_from_hh_id


def test_vacancy_url_from_hh_id_numeric() -> None:
    assert vacancy_url_from_hh_id("12345") == "https://hh.ru/vacancy/12345"


def test_vacancy_url_from_hh_id_full_url() -> None:
    u = "https://hh.ru/vacancy/999"
    assert vacancy_url_from_hh_id(u) == u


def test_normalize_hh_vacancy_url_relative() -> None:
    assert normalize_hh_vacancy_url("/vacancy/1", "1") == "https://hh.ru/vacancy/1"


def test_normalize_hh_vacancy_url_fallback() -> None:
    assert normalize_hh_vacancy_url("", "42") == "https://hh.ru/vacancy/42"
