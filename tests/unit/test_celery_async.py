"""Tests for celery_async helpers."""

from src.core.celery_async import normalize_celery_task_id


def test_normalize_celery_task_id_accepts_uuid_string() -> None:
    s = "fcc31538-deb3-48e9-afc3-49c229f1cb39"
    assert normalize_celery_task_id(s) == s


def test_normalize_celery_task_id_coerces_int() -> None:
    assert normalize_celery_task_id(56) == "56"


def test_normalize_celery_task_id_decodes_bytes() -> None:
    assert normalize_celery_task_id(b"abc-123") == "abc-123"


def test_normalize_celery_task_id_none_and_empty() -> None:
    assert normalize_celery_task_id(None) is None
    assert normalize_celery_task_id("") is None
    assert normalize_celery_task_id("   ") is None
