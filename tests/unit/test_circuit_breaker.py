import time
from unittest.mock import MagicMock

import pytest

from src.worker.circuit_breaker import (
    STATE_CLOSED,
    STATE_HALF_OPEN,
    STATE_OPEN,
    CircuitBreaker,
)


@pytest.fixture
def mock_redis():
    store: dict[str, bytes] = {}

    redis_mock = MagicMock()

    def get(key):
        return store.get(key)

    def set(key, value):
        store[key] = value.encode() if isinstance(value, str) else str(value).encode()

    def incr(key):
        current = int(store.get(key, b"0"))
        store[key] = str(current + 1).encode()
        return current + 1

    redis_mock.get = MagicMock(side_effect=get)
    redis_mock.set = MagicMock(side_effect=set)
    redis_mock.incr = MagicMock(side_effect=incr)

    return redis_mock


class TestCircuitBreaker:
    def test_initial_state_is_closed(self, mock_redis):
        cb = CircuitBreaker("test", redis_client=mock_redis)
        assert cb.state == STATE_CLOSED

    def test_allows_calls_when_closed(self, mock_redis):
        cb = CircuitBreaker("test", redis_client=mock_redis)
        assert cb.is_call_allowed()

    def test_opens_after_threshold_failures(self, mock_redis):
        cb = CircuitBreaker("test", failure_threshold=3, redis_client=mock_redis)

        for _ in range(3):
            cb.record_failure()

        assert cb.state == STATE_OPEN

    def test_rejects_calls_when_open(self, mock_redis):
        cb = CircuitBreaker("test", failure_threshold=1, redis_client=mock_redis)
        cb.record_failure()
        assert not cb.is_call_allowed()

    def test_transitions_to_half_open_after_recovery(self, mock_redis):
        cb = CircuitBreaker(
            "test",
            failure_threshold=1,
            recovery_timeout=0,
            redis_client=mock_redis,
        )
        cb.record_failure()

        mock_redis.get.side_effect = lambda key: {
            "cb:test:state": b"open",
            "cb:test:failures": b"1",
            "cb:test:last_failure_time": str(time.time() - 10).encode(),
        }.get(key)

        assert cb.is_call_allowed()

    def test_closes_on_success_after_half_open(self, mock_redis):
        cb = CircuitBreaker("test", redis_client=mock_redis)
        cb.state = STATE_HALF_OPEN
        cb.record_success()
        assert cb.state == STATE_CLOSED

    def test_force_open(self, mock_redis):
        cb = CircuitBreaker("test", redis_client=mock_redis)
        cb.force_open()
        assert cb.state == STATE_OPEN

    def test_force_close(self, mock_redis):
        cb = CircuitBreaker("test", failure_threshold=1, redis_client=mock_redis)
        cb.record_failure()
        cb.force_close()
        assert cb.state == STATE_CLOSED
        assert cb.failure_count == 0
