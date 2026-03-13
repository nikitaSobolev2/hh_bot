"""Tests for the Redis-backed circuit breaker."""

import time
from unittest.mock import MagicMock

import pytest

from src.worker.circuit_breaker import (
    STATE_CLOSED,
    STATE_OPEN,
    CircuitBreaker,
)


@pytest.fixture
def mock_redis():
    """Fake Redis that supports get/set/incr/decr/expire/delete and pipeline()."""
    store: dict[str, bytes] = {}

    redis_mock = MagicMock()

    def get(key):
        return store.get(key)

    def set(key, value, ex=None):
        store[key] = value.encode() if isinstance(value, str) else str(value).encode()

    def incr(key):
        current = int(store.get(key, b"0"))
        store[key] = str(current + 1).encode()
        return current + 1

    def decr(key):
        current = int(store.get(key, b"0"))
        store[key] = str(current - 1).encode()
        return current - 1

    def expire(key, seconds):
        pass

    def delete(*keys):
        for k in keys:
            store.pop(k, None)

    redis_mock.get = MagicMock(side_effect=get)
    redis_mock.set = MagicMock(side_effect=set)
    redis_mock.incr = MagicMock(side_effect=incr)
    redis_mock.decr = MagicMock(side_effect=decr)
    redis_mock.expire = MagicMock(side_effect=expire)
    redis_mock.delete = MagicMock(side_effect=delete)

    pipe_mock = MagicMock()
    pipe_mock.__enter__ = MagicMock(return_value=pipe_mock)
    pipe_mock.__exit__ = MagicMock(return_value=False)
    pipe_mock.set = MagicMock(side_effect=set)
    pipe_mock.delete = MagicMock(side_effect=delete)
    pipe_mock.execute = MagicMock(return_value=[])
    redis_mock.pipeline = MagicMock(return_value=pipe_mock)

    return redis_mock, store


class TestCircuitBreakerInitialState:
    def test_initial_state_is_closed(self, mock_redis):
        redis, _ = mock_redis
        cb = CircuitBreaker("test", redis_client=redis)
        assert cb.state == STATE_CLOSED

    def test_allows_calls_when_closed(self, mock_redis):
        redis, _ = mock_redis
        cb = CircuitBreaker("test", redis_client=redis)
        assert cb.is_call_allowed() is True


class TestCircuitBreakerFailureHandling:
    def test_failure_count_increments_on_each_failure(self, mock_redis):
        redis, _ = mock_redis
        cb = CircuitBreaker("test", failure_threshold=5, redis_client=redis)
        cb.record_failure()
        assert cb.failure_count == 1

    def test_opens_after_threshold_failures(self, mock_redis):
        redis, _ = mock_redis
        cb = CircuitBreaker("test", failure_threshold=3, redis_client=redis)

        for _ in range(3):
            cb.record_failure()

        assert cb.state == STATE_OPEN

    def test_rejects_calls_when_open(self, mock_redis):
        redis, store = mock_redis
        cb = CircuitBreaker("test", failure_threshold=1, redis_client=redis)
        cb.record_failure()

        store["cb:test:last_failure_time"] = str(time.time()).encode()

        assert cb.is_call_allowed() is False


class TestCircuitBreakerRecovery:
    def test_transitions_to_half_open_after_recovery_timeout(self, mock_redis):
        redis, store = mock_redis
        cb = CircuitBreaker(
            "test",
            failure_threshold=1,
            recovery_timeout=0,
            redis_client=redis,
        )
        store["cb:test:state"] = b"open"
        store["cb:test:last_failure_time"] = str(time.time() - 10).encode()

        assert cb.is_call_allowed() is True

    def test_closes_on_success_when_half_open_threshold_reached(self, mock_redis):
        redis, store = mock_redis
        store["cb:test:state"] = b"half_open"
        store["cb:test:half_open_successes"] = b"0"

        cb = CircuitBreaker(
            "test",
            half_open_success_threshold=1,
            redis_client=redis,
        )
        cb.record_success()
        assert cb.state == STATE_CLOSED

    def test_reopens_on_failure_when_half_open(self, mock_redis):
        redis, store = mock_redis
        store["cb:test:state"] = b"half_open"
        store["cb:test:failures"] = b"0"

        cb = CircuitBreaker(
            "test",
            failure_threshold=3,
            redis_client=redis,
        )
        cb.record_failure()
        assert cb.state == STATE_OPEN


class TestCircuitBreakerAdminOperations:
    def test_force_open_transitions_to_open(self, mock_redis):
        redis, _ = mock_redis
        cb = CircuitBreaker("test", redis_client=redis)
        cb.force_open()
        assert cb.state == STATE_OPEN

    def test_force_close_resets_to_closed_and_clears_failures(self, mock_redis):
        redis, store = mock_redis
        store["cb:test:state"] = b"open"
        store["cb:test:failures"] = b"7"

        cb = CircuitBreaker("test", redis_client=redis)
        cb.force_close()

        assert cb.state == STATE_CLOSED
        assert cb.failure_count == 0

    def test_update_config_changes_threshold(self, mock_redis):
        redis, _ = mock_redis
        cb = CircuitBreaker("test", failure_threshold=5, redis_client=redis)
        cb.update_config(failure_threshold=2)
        assert cb._failure_threshold == 2


class TestCircuitBreakerRateLimiter:
    def test_parse_achievement_blocks_returns_company_as_key(self):
        """Test the _parse_achievement_blocks function from achievements task."""
        from src.worker.tasks.achievements import _parse_achievement_blocks

        text = "[AchStart]:Acme Corp\nDid great work\n[AchEnd]:Acme Corp"
        result = _parse_achievement_blocks(text)
        assert "Acme Corp" in result

    def test_parse_achievement_blocks_returns_content_as_value(self):
        from src.worker.tasks.achievements import _parse_achievement_blocks

        text = "[AchStart]:Acme Corp\nDid great work\n[AchEnd]:Acme Corp"
        result = _parse_achievement_blocks(text)
        assert result["Acme Corp"] == "Did great work"

    def test_parse_achievement_blocks_handles_multiple_companies(self):
        from src.worker.tasks.achievements import _parse_achievement_blocks

        text = (
            "[AchStart]:Company1\nAchievement 1\n[AchEnd]:Company1\n"
            "[AchStart]:Company2\nAchievement 2\n[AchEnd]:Company2"
        )
        result = _parse_achievement_blocks(text)
        assert len(result) == 2

    def test_parse_achievement_blocks_returns_empty_on_no_match(self):
        from src.worker.tasks.achievements import _parse_achievement_blocks

        result = _parse_achievement_blocks("no blocks here")
        assert result == {}
