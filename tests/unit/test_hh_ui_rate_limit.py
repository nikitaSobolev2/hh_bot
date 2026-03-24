"""Tests for HH UI apply rate limiting."""

from unittest.mock import MagicMock, patch

import pytest

from src.services.hh_ui.rate_limit import (
    current_ui_apply_count_sync,
    remaining_ui_apply_slots_sync,
    try_acquire_ui_apply_slot_sync,
)


@pytest.fixture
def mock_settings():
    with patch("src.services.hh_ui.rate_limit.settings") as s:
        s.hh_ui_apply_max_per_day = 2
        s.redis_url = "redis://localhost:9/0"
        yield s


def test_rate_limit_allows_within_limit(mock_settings) -> None:
    r = MagicMock()
    r.incr.side_effect = [1, 2]
    r.ttl.return_value = -1
    r.expire.return_value = True
    with patch("src.services.hh_ui.rate_limit.sync_redis.Redis.from_url", return_value=r):
        assert try_acquire_ui_apply_slot_sync(1) is True
        assert try_acquire_ui_apply_slot_sync(1) is True


def test_rate_limit_blocks_over_limit(mock_settings) -> None:
    r = MagicMock()
    r.incr.side_effect = [3]
    r.ttl.return_value = 3600
    r.decr.return_value = 2
    with patch("src.services.hh_ui.rate_limit.sync_redis.Redis.from_url", return_value=r):
        assert try_acquire_ui_apply_slot_sync(1) is False


def test_current_ui_apply_count_reads_redis(mock_settings) -> None:
    r = MagicMock()
    r.get.return_value = "7"
    with patch("src.services.hh_ui.rate_limit.sync_redis.Redis.from_url", return_value=r):
        assert current_ui_apply_count_sync(42) == 7
    r.get.assert_called_once()


def test_current_ui_apply_count_missing_key(mock_settings) -> None:
    r = MagicMock()
    r.get.return_value = None
    with patch("src.services.hh_ui.rate_limit.sync_redis.Redis.from_url", return_value=r):
        assert current_ui_apply_count_sync(42) == 0


def test_remaining_ui_apply_slots_unlimited(mock_settings) -> None:
    mock_settings.hh_ui_apply_max_per_day = 0
    assert remaining_ui_apply_slots_sync(1) is None


def test_remaining_ui_apply_slots(mock_settings) -> None:
    r = MagicMock()
    r.get.return_value = "1"
    with patch("src.services.hh_ui.rate_limit.sync_redis.Redis.from_url", return_value=r):
        assert remaining_ui_apply_slots_sync(99) == 1
