"""Tests for Celery captcha retry countdown helper."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from src.worker.hh_captcha_retry import celery_captcha_retry_countdown


def test_celery_captcha_retry_countdown_exponential_cap():
    task = MagicMock()
    task.request.retries = 0
    assert celery_captcha_retry_countdown(task) == 10
    task.request.retries = 1
    assert celery_captcha_retry_countdown(task) == 20
    task.request.retries = 2
    assert celery_captcha_retry_countdown(task) == 40
    task.request.retries = 4
    assert celery_captcha_retry_countdown(task) == 160
    task.request.retries = 5
    assert celery_captcha_retry_countdown(task) == 300
    task.request.retries = 10
    assert celery_captcha_retry_countdown(task) == 300


def test_celery_captcha_retry_countdown_none_retries_treated_as_zero():
    task = MagicMock()
    task.request = SimpleNamespace(retries=None)
    assert celery_captcha_retry_countdown(task) == 10
