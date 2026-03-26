"""Tests for Celery captcha retry countdown helper."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from src.worker.hh_captcha_retry import celery_captcha_retry_countdown


def test_celery_captcha_retry_countdown_exponential_cap():
    """Exponential leg when circuit recovery is small (matches old pure-exponential behavior)."""
    task = MagicMock()
    task.request.retries = 0
    assert celery_captcha_retry_countdown(task, circuit_recovery_seconds=10) == 10
    task.request.retries = 1
    assert celery_captcha_retry_countdown(task, circuit_recovery_seconds=10) == 20
    task.request.retries = 2
    assert celery_captcha_retry_countdown(task, circuit_recovery_seconds=10) == 40
    task.request.retries = 4
    assert celery_captcha_retry_countdown(task, circuit_recovery_seconds=10) == 160
    task.request.retries = 5
    assert celery_captcha_retry_countdown(task, circuit_recovery_seconds=10) == 300
    task.request.retries = 10
    assert celery_captcha_retry_countdown(task, circuit_recovery_seconds=10) == 300


def test_celery_captcha_retry_countdown_none_retries_treated_as_zero():
    task = MagicMock()
    task.request = SimpleNamespace(retries=None)
    assert celery_captcha_retry_countdown(task, circuit_recovery_seconds=10) == 10


def test_celery_captcha_retry_countdown_waits_at_least_recovery():
    """Countdown is at least the Redis circuit recovery window (default 300s)."""
    task = MagicMock()
    task.request.retries = 0
    assert celery_captcha_retry_countdown(task, circuit_recovery_seconds=300) == 300
    task.request.retries = 2
    assert celery_captcha_retry_countdown(task, circuit_recovery_seconds=300) == 300


def test_celery_captcha_retry_countdown_long_recovery_not_truncated():
    """If env sets a recovery longer than the exponential cap, Celery waits for that window."""
    task = MagicMock()
    task.request.retries = 0
    assert celery_captcha_retry_countdown(task, circuit_recovery_seconds=900) == 900
