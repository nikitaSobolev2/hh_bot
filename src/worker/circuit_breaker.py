"""Redis-backed circuit breaker for Celery tasks.

States:
  CLOSED  — normal operation, calls pass through
  OPEN    — failing, calls are rejected
  HALF_OPEN — testing recovery, one call allowed
"""

import time

import redis

from src.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

STATE_CLOSED = "closed"
STATE_OPEN = "open"
STATE_HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        redis_client: redis.Redis | None = None,
    ) -> None:
        self._name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._redis = redis_client or redis.Redis.from_url(settings.redis_url)

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
    def state(self) -> str:
        raw = self._redis.get(self._key_state)
        if raw is None:
            return STATE_CLOSED
        return raw.decode()

    @state.setter
    def state(self, value: str) -> None:
        self._redis.set(self._key_state, value)

    @property
    def failure_count(self) -> int:
        raw = self._redis.get(self._key_failures)
        return int(raw) if raw else 0

    def is_call_allowed(self) -> bool:
        current_state = self.state

        if current_state == STATE_CLOSED:
            return True

        if current_state == STATE_OPEN:
            last_failure = self._redis.get(self._key_last_failure)
            if last_failure:
                elapsed = time.time() - float(last_failure)
                if elapsed >= self._recovery_timeout:
                    self.state = STATE_HALF_OPEN
                    logger.info("Circuit breaker half-open", name=self._name)
                    return True
            return False

        return current_state == STATE_HALF_OPEN

    def record_success(self) -> None:
        if self.state in (STATE_HALF_OPEN, STATE_OPEN):
            logger.info("Circuit breaker closed after success", name=self._name)

        self._redis.set(self._key_state, STATE_CLOSED)
        self._redis.set(self._key_failures, 0)

    def record_failure(self) -> None:
        failures = self._redis.incr(self._key_failures)
        self._redis.set(self._key_last_failure, str(time.time()))

        if failures >= self._failure_threshold:
            self._redis.set(self._key_state, STATE_OPEN)
            logger.warning(
                "Circuit breaker opened",
                name=self._name,
                failures=failures,
            )

    def force_open(self) -> None:
        self.state = STATE_OPEN
        logger.info("Circuit breaker force-opened", name=self._name)

    def force_close(self) -> None:
        self.state = STATE_CLOSED
        self._redis.set(self._key_failures, 0)
        logger.info("Circuit breaker force-closed", name=self._name)

    def update_config(
        self,
        failure_threshold: int | None = None,
        recovery_timeout: int | None = None,
    ) -> None:
        if failure_threshold is not None:
            self._failure_threshold = failure_threshold
        if recovery_timeout is not None:
            self._recovery_timeout = recovery_timeout
