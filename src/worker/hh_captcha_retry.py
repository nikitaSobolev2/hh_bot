"""Celery retry delays for HH captcha / circuit-open (separate from Redis circuit recovery TTL)."""

from __future__ import annotations

# First retry after 10s, then 20, 40, 80, 160, then cap at 300s.
_CAPTCHA_RETRY_BASE_SECONDS = 10
_CAPTCHA_RETRY_MAX_SECONDS = 300


def celery_captcha_retry_countdown(task) -> int:
    """Exponential backoff for scheduling the next attempt: min(10 * 2**retries, 300)."""
    retries = getattr(task.request, "retries", None) or 0
    return min(_CAPTCHA_RETRY_BASE_SECONDS * (2**retries), _CAPTCHA_RETRY_MAX_SECONDS)
