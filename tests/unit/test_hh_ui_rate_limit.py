"""Tests for HH UI apply rate limiting."""

from unittest.mock import MagicMock, patch

import pytest

from src.services.hh_ui.rate_limit import try_acquire_ui_apply_slot_sync


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
