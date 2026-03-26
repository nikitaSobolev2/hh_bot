"""Celery retry delays for HH captcha / circuit-open.

Must wait at least as long as the Redis ``hh_public_api`` circuit recovery window,
otherwise the next attempt hits ``circuit open`` immediately. The exponential leg is
capped at 300s and **cycles**: 10, 20, 40, 80, 160, 300, then back to 10. The scheduled
delay is ``max(exponential, recovery_seconds)``.
"""

from __future__ import annotations

# Exponential leg: 10, 20, 40, 80, 160, 300 — then repeats (same as 6 steps before 2**6 would exceed cap).
_CAPTCHA_RETRY_BASE_SECONDS = 10
_CAPTCHA_RETRY_MAX_SECONDS = 300
_CAPTCHA_EXPONENT_CYCLE_LENGTH = 6


def celery_captcha_retry_countdown(task, *, circuit_recovery_seconds: int | None = None) -> int:
    """Seconds until next Celery attempt.

    Returns max(exponential, redis_recovery) so the HH public API circuit can leave
    OPEN before we retry. Exponential backoff resets after the 300s step.
    """
    from src.config import settings

    recovery = circuit_recovery_seconds
    if recovery is None:
        recovery = int(settings.hh_public_api_circuit_recovery_seconds)
    recovery = int(recovery)

    retries = getattr(task.request, "retries", None) or 0
    # Cycle exponent so delays do not stay at 300 forever: ... 300 → next retry uses 10 again.
    exp = retries % _CAPTCHA_EXPONENT_CYCLE_LENGTH
    exponential = min(_CAPTCHA_RETRY_BASE_SECONDS * (2**exp), _CAPTCHA_RETRY_MAX_SECONDS)
    # Do not cap recovery at 300: env may set a longer Redis TTL than the exponential cap.
    return max(exponential, recovery)
