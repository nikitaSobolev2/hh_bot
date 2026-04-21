"""Redis-backed circuit breaker for Celery tasks.

States:
  CLOSED    — normal operation, calls pass through
  OPEN      — failing, calls are rejected until recovery_timeout elapses
  HALF_OPEN — testing recovery; requires ``half_open_success_threshold``
               consecutive successes before transitioning back to CLOSED

Key improvements over naive implementations:
- All Redis keys carry a TTL (``_STATE_TTL``) so stale entries self-expire.
- HALF_OPEN requires multiple consecutive successes (configurable).
- Transitions use pipelined writes to reduce round-trips.
"""

from __future__ import annotations

import time

import redis

from src.config import settings
from src.core.constants import (
    CB_DEFAULT_FAILURE_THRESHOLD,
    CB_DEFAULT_RECOVERY_TIMEOUT,
    CB_HALF_OPEN_SUCCESS_THRESHOLD,
    REDIS_CB_FAILURES_TTL,
    REDIS_CB_STATE_TTL,
)
from src.core.logging import get_logger

logger = get_logger(__name__)

STATE_CLOSED = "closed"
STATE_OPEN = "open"
STATE_HALF_OPEN = "half_open"


class CircuitBreaker:
    """Redis-backed circuit breaker.

    Thread-safe via Redis atomic operations.  Uses synchronous Redis because
    Celery tasks run inside ``asyncio.run()`` and we need the circuit breaker
    before the event loop is available.
    """

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = CB_DEFAULT_FAILURE_THRESHOLD,
        recovery_timeout: int = CB_DEFAULT_RECOVERY_TIMEOUT,
        half_open_success_threshold: int = CB_HALF_OPEN_SUCCESS_THRESHOLD,
        redis_client: redis.Redis | None = None,
        exponential_recovery: bool = False,
        recovery_multiplier: float = 2.0,
        max_recovery_timeout: int | None = None,
    ) -> None:
        self._name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_success_threshold = half_open_success_threshold
        self._exponential_recovery = exponential_recovery
        self._recovery_multiplier = recovery_multiplier
        self._max_recovery_timeout = max_recovery_timeout
        self._redis = redis_client or redis.Redis.from_url(settings.redis_url)

    # ------------------------------------------------------------------
    # Redis key helpers
    # ------------------------------------------------------------------

    @property
    def _key_state(self) -> str:
        return f"cb:{self._name}:state"

    @property
    def _key_failures(self) -> str:
        return f"cb:{self._name}:failures"

    @property
    def _key_last_failure(self) -> str:
        return f"cb:{self._name}:last_failure_time"

    @property
    def _key_half_open_successes(self) -> str:
        return f"cb:{self._name}:half_open_successes"

    @property
    def _key_open_streak(self) -> str:
        return f"cb:{self._name}:open_streak"

    @property
    def _key_effective_recovery(self) -> str:
        return f"cb:{self._name}:effective_recovery_seconds"

    # ------------------------------------------------------------------
    # State accessors
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        raw = self._redis.get(self._key_state)
        if raw is None:
            return STATE_CLOSED
        return raw.decode() if isinstance(raw, bytes) else raw

    @property
    def failure_count(self) -> int:
        raw = self._redis.get(self._key_failures)
        return int(raw) if raw else 0

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    def is_call_allowed(self) -> bool:
        """Return True when the breaker is CLOSED or HALF_OPEN."""
        current_state = self.state

        if current_state == STATE_CLOSED:
            return True

        if current_state == STATE_OPEN:
            last_failure = self._redis.get(self._key_last_failure)
            if last_failure:
                elapsed = time.time() - float(last_failure)
                recovery_seconds = float(self._recovery_timeout)
                if self._exponential_recovery:
                    raw_eff = self._redis.get(self._key_effective_recovery)
                    if raw_eff is not None:
                        recovery_seconds = float(
                            raw_eff.decode() if isinstance(raw_eff, bytes) else raw_eff
                        )
                if elapsed >= recovery_seconds:
                    self._transition_to_half_open()
                    return True
            return False

        return current_state == STATE_HALF_OPEN

    def record_success(self) -> None:
        """Record a successful call.  May close the breaker from HALF_OPEN."""
        current_state = self.state

        if current_state == STATE_HALF_OPEN:
            successes = self._redis.incr(self._key_half_open_successes)
            self._redis.expire(self._key_half_open_successes, REDIS_CB_STATE_TTL)
            if successes >= self._half_open_success_threshold:
                self._transition_to_closed()
        elif current_state == STATE_OPEN:
            self._transition_to_closed()
        else:
            with self._redis.pipeline() as pipe:
                pipe.set(self._key_failures, 0, ex=REDIS_CB_FAILURES_TTL)
                pipe.execute()

    def record_failure(self) -> None:
        """Record a failed call.  May open the breaker."""
        failures = self._redis.incr(self._key_failures)
        self._redis.expire(self._key_failures, REDIS_CB_FAILURES_TTL)

        with self._redis.pipeline() as pipe:
            pipe.set(self._key_last_failure, str(time.time()), ex=REDIS_CB_STATE_TTL)
            pipe.execute()

        if self.state == STATE_HALF_OPEN:
            self._transition_to_open(failures)
            return

        if failures >= self._failure_threshold:
            self._transition_to_open(failures)

    def force_open(self) -> None:
        """Administratively open the breaker (e.g. via admin panel)."""
        self._transition_to_open(self._failure_threshold)
        logger.info("Circuit breaker force-opened", name=self._name)

    def force_close(self) -> None:
        """Administratively close the breaker (e.g. via admin panel)."""
        self._transition_to_closed()
        logger.info("Circuit breaker force-closed", name=self._name)

    def update_config(
        self,
        failure_threshold: int | None = None,
        recovery_timeout: int | None = None,
        half_open_success_threshold: int | None = None,
    ) -> None:
        """Update runtime configuration values."""
        if failure_threshold is not None:
            self._failure_threshold = failure_threshold
        if recovery_timeout is not None:
            self._recovery_timeout = recovery_timeout
        if half_open_success_threshold is not None:
            self._half_open_success_threshold = half_open_success_threshold

    # ------------------------------------------------------------------
    # Internal state transitions
    # ------------------------------------------------------------------

    def _transition_to_open(self, failures: int) -> None:
        effective_recovery = self._recovery_timeout
        if self._exponential_recovery:
            streak = int(self._redis.incr(self._key_open_streak))
            self._redis.expire(self._key_open_streak, REDIS_CB_STATE_TTL)
            cap = self._max_recovery_timeout or self._recovery_timeout
            base = float(self._recovery_timeout)
            mult = self._recovery_multiplier
            effective_recovery = int(min(base * (mult ** (streak - 1)), float(cap)))
            self._redis.set(
                self._key_effective_recovery,
                str(effective_recovery),
                ex=REDIS_CB_STATE_TTL,
            )
        with self._redis.pipeline() as pipe:
            pipe.set(self._key_state, STATE_OPEN, ex=REDIS_CB_STATE_TTL)
            pipe.delete(self._key_half_open_successes)
            pipe.execute()
        logger.warning(
            "Circuit breaker opened",
            name=self._name,
            failures=failures,
            threshold=self._failure_threshold,
            effective_recovery_seconds=(
                effective_recovery if self._exponential_recovery else None
            ),
        )

    def _transition_to_half_open(self) -> None:
        with self._redis.pipeline() as pipe:
            pipe.set(self._key_state, STATE_HALF_OPEN, ex=REDIS_CB_STATE_TTL)
            pipe.set(self._key_half_open_successes, 0, ex=REDIS_CB_STATE_TTL)
            pipe.execute()
        logger.info("Circuit breaker half-open", name=self._name)

    def _transition_to_closed(self) -> None:
        with self._redis.pipeline() as pipe:
            pipe.set(self._key_state, STATE_CLOSED, ex=REDIS_CB_STATE_TTL)
            pipe.set(self._key_failures, 0, ex=REDIS_CB_FAILURES_TTL)
            pipe.delete(self._key_half_open_successes)
            pipe.delete(self._key_open_streak)
            pipe.delete(self._key_effective_recovery)
            pipe.execute()
        logger.info("Circuit breaker closed", name=self._name)
