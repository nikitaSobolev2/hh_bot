"""SystemLoadGuard threshold + backoff + recovery behavior."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.core.system_load import (
    SystemLoadGuard,
    SystemLoadSample,
)


def _sample(cpu: float = 10.0, ram: float = 10.0, disk: float = 10.0) -> SystemLoadSample:
    return SystemLoadSample(cpu_percent=cpu, ram_percent=ram, disk_percent=disk)


def test_is_overloaded_returns_false_when_all_metrics_under_thresholds() -> None:
    guard = SystemLoadGuard(sampler=lambda: _sample(50, 50, 50))
    overloaded, reason = guard.is_overloaded()
    assert overloaded is False
    assert reason is None


def test_is_overloaded_returns_cpu_when_cpu_exceeds_pause_threshold() -> None:
    guard = SystemLoadGuard(sampler=lambda: _sample(cpu=99, ram=10, disk=10))
    overloaded, reason = guard.is_overloaded()
    assert overloaded is True
    assert reason == "cpu"


def test_is_overloaded_returns_ram_when_ram_exceeds_pause_threshold() -> None:
    guard = SystemLoadGuard(sampler=lambda: _sample(cpu=10, ram=95, disk=10))
    overloaded, reason = guard.is_overloaded()
    assert overloaded is True
    assert reason == "ram"


def test_is_overloaded_returns_disk_when_disk_exceeds_pause_threshold() -> None:
    guard = SystemLoadGuard(sampler=lambda: _sample(cpu=10, ram=10, disk=99))
    overloaded, reason = guard.is_overloaded()
    assert overloaded is True
    assert reason == "disk"


@pytest.mark.asyncio
async def test_wait_if_overloaded_returns_immediately_when_healthy() -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    guard = SystemLoadGuard(
        sampler=lambda: _sample(20, 20, 20),
        sleeper_async=fake_sleep,
    )
    result = await guard.wait_if_overloaded("test")
    assert sleeps == []
    assert result.cpu_percent == 20


@pytest.mark.asyncio
async def test_wait_if_overloaded_backs_off_until_recovery_threshold_with_hysteresis() -> None:
    """Once overloaded, the guard must drop below pause-hysteresis before resuming."""
    samples = iter(
        [
            _sample(cpu=99, ram=10, disk=10),
            _sample(cpu=90, ram=10, disk=10),
            _sample(cpu=87, ram=10, disk=10),
            _sample(cpu=80, ram=10, disk=10),
        ]
    )
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    guard = SystemLoadGuard(
        sampler=lambda: next(samples),
        sleeper_async=fake_sleep,
    )
    with patch("src.core.system_load.settings") as mock_settings:
        mock_settings.system_load_cpu_pause_percent = 92
        mock_settings.system_load_ram_pause_percent = 90
        mock_settings.system_load_disk_pause_percent = 97
        mock_settings.system_load_backoff_max_seconds = 30

        result = await guard.wait_if_overloaded("apply_pump_test")

    assert result.cpu_percent == 80
    assert sleeps == [1.0, 2.0, 4.0]


@pytest.mark.asyncio
async def test_wait_if_overloaded_caps_backoff_at_max_seconds() -> None:
    """Backoff doubles but must clamp to the configured ceiling."""
    counter = {"n": 0}

    def sampler() -> SystemLoadSample:
        counter["n"] += 1
        if counter["n"] < 8:
            return _sample(cpu=99, ram=10, disk=10)
        return _sample(cpu=20, ram=10, disk=10)

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    guard = SystemLoadGuard(sampler=sampler, sleeper_async=fake_sleep)
    with patch("src.core.system_load.settings") as mock_settings:
        mock_settings.system_load_cpu_pause_percent = 92
        mock_settings.system_load_ram_pause_percent = 90
        mock_settings.system_load_disk_pause_percent = 97
        mock_settings.system_load_backoff_max_seconds = 8

        await guard.wait_if_overloaded("test_cap")

    assert sleeps[-1] == 8.0
    assert all(s <= 8.0 for s in sleeps)


def test_wait_if_overloaded_sync_blocks_until_resume() -> None:
    samples = iter(
        [
            _sample(cpu=99, ram=10, disk=10),
            _sample(cpu=80, ram=10, disk=10),
        ]
    )
    sleeps: list[float] = []

    guard = SystemLoadGuard(
        sampler=lambda: next(samples),
        sleeper_sync=lambda s: sleeps.append(s),
    )
    with patch("src.core.system_load.settings") as mock_settings:
        mock_settings.system_load_cpu_pause_percent = 92
        mock_settings.system_load_ram_pause_percent = 90
        mock_settings.system_load_disk_pause_percent = 97
        mock_settings.system_load_backoff_max_seconds = 30

        result = guard.wait_if_overloaded_sync("playwright_thread")

    assert result.cpu_percent == 80
    assert sleeps == [1.0]
