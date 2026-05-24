"""psutil-based throttler that pauses dispatchers when CPU / RAM / disk run hot.

The autorespond pipeline (dispatcher, cover-letter pregenerate, apply pump)
samples this guard between work units to back off when the host is saturated.

Usage
-----
    from src.core.system_load import get_system_load_guard

    guard = get_system_load_guard()
    await guard.wait_if_overloaded("apply_pump_between_batches")

Sync variant for non-async callers (Playwright thread, beat tasks)::

    guard.wait_if_overloaded_sync("...")

Thresholds come from ``settings.system_load_*``. A 5-point hysteresis avoids
flapping: once paused, the guard waits until the metric drops to
``threshold - 5`` before resuming.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass

import psutil

from src.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

_HYSTERESIS_PERCENT = 5
_BACKOFF_INITIAL_SECONDS = 1.0
_BACKOFF_MULTIPLIER = 2.0


@dataclass(frozen=True)
class SystemLoadSample:
    """One snapshot of CPU / RAM / disk usage percentages."""

    cpu_percent: float
    ram_percent: float
    disk_percent: float

    def overloaded(
        self,
        *,
        cpu_limit: float,
        ram_limit: float,
        disk_limit: float,
    ) -> tuple[bool, str | None]:
        """Return (overloaded?, dominant_reason). Reason is the metric that broke."""
        if self.cpu_percent >= cpu_limit:
            return True, "cpu"
        if self.ram_percent >= ram_limit:
            return True, "ram"
        if self.disk_percent >= disk_limit:
            return True, "disk"
        return False, None


SampleFn = Callable[[], SystemLoadSample]


def _default_sampler() -> SystemLoadSample:
    """psutil-backed sampler. ``cpu_percent(interval=0.0)`` returns the prior tick."""
    return SystemLoadSample(
        cpu_percent=float(psutil.cpu_percent(interval=0.0)),
        ram_percent=float(psutil.virtual_memory().percent),
        disk_percent=float(psutil.disk_usage("/").percent),
    )


class SystemLoadGuard:
    """Pauses callers when host metrics exceed configured thresholds.

    The guard is intentionally stateless beyond its sampler — every check
    reads fresh psutil values. Hysteresis is applied via the resume threshold
    being lower than the pause threshold.

    Backoff is exponential per consecutive wait, capped at
    ``settings.system_load_backoff_max_seconds``. Once a sample is healthy,
    the backoff resets.
    """

    def __init__(
        self,
        *,
        sampler: SampleFn | None = None,
        sleeper_async=None,
        sleeper_sync=None,
    ) -> None:
        self._sample = sampler or _default_sampler
        # Tests inject deterministic sleepers; production uses asyncio.sleep / time.sleep.
        self._sleep_async = sleeper_async or asyncio.sleep
        self._sleep_sync = sleeper_sync or time.sleep

    @property
    def cpu_pause_percent(self) -> float:
        return float(settings.system_load_cpu_pause_percent)

    @property
    def ram_pause_percent(self) -> float:
        return float(settings.system_load_ram_pause_percent)

    @property
    def disk_pause_percent(self) -> float:
        return float(settings.system_load_disk_pause_percent)

    @property
    def backoff_max_seconds(self) -> float:
        return float(settings.system_load_backoff_max_seconds)

    def _resume_threshold(self, pause_threshold: float) -> float:
        return max(0.0, pause_threshold - _HYSTERESIS_PERCENT)

    def sample(self) -> SystemLoadSample:
        return self._sample()

    def is_overloaded(self, sample: SystemLoadSample | None = None) -> tuple[bool, str | None]:
        """True when any pause threshold is hit. Use ``wait_if_overloaded`` to block."""
        snap = sample or self._sample()
        return snap.overloaded(
            cpu_limit=self.cpu_pause_percent,
            ram_limit=self.ram_pause_percent,
            disk_limit=self.disk_pause_percent,
        )

    def _resume_ready(self, sample: SystemLoadSample) -> bool:
        """Recovery uses pause_threshold - hysteresis so we don't oscillate."""
        return (
            sample.cpu_percent < self._resume_threshold(self.cpu_pause_percent)
            and sample.ram_percent < self._resume_threshold(self.ram_pause_percent)
            and sample.disk_percent < self._resume_threshold(self.disk_pause_percent)
        )

    def _next_backoff(self, current: float) -> float:
        if current <= 0:
            return _BACKOFF_INITIAL_SECONDS
        return min(current * _BACKOFF_MULTIPLIER, self.backoff_max_seconds)

    async def wait_if_overloaded(self, reason: str) -> SystemLoadSample:
        """Async: block while overloaded; return the first healthy sample seen."""
        sample = self._sample()
        overloaded, dominant = self.is_overloaded(sample)
        if not overloaded:
            return sample

        logger.warning(
            "system_load_pause",
            reason=reason,
            dominant=dominant,
            cpu_percent=round(sample.cpu_percent, 1),
            ram_percent=round(sample.ram_percent, 1),
            disk_percent=round(sample.disk_percent, 1),
        )
        backoff = _BACKOFF_INITIAL_SECONDS
        total_waited = 0.0
        while True:
            await self._sleep_async(backoff)
            total_waited += backoff
            sample = self._sample()
            if self._resume_ready(sample):
                logger.info(
                    "system_load_resume",
                    reason=reason,
                    waited_seconds=round(total_waited, 1),
                    cpu_percent=round(sample.cpu_percent, 1),
                    ram_percent=round(sample.ram_percent, 1),
                    disk_percent=round(sample.disk_percent, 1),
                )
                return sample
            backoff = self._next_backoff(backoff)

    def wait_if_overloaded_sync(self, reason: str) -> SystemLoadSample:
        """Sync variant for Playwright thread / beat-task contexts."""
        sample = self._sample()
        overloaded, dominant = self.is_overloaded(sample)
        if not overloaded:
            return sample

        logger.warning(
            "system_load_pause",
            reason=reason,
            dominant=dominant,
            cpu_percent=round(sample.cpu_percent, 1),
            ram_percent=round(sample.ram_percent, 1),
            disk_percent=round(sample.disk_percent, 1),
        )
        backoff = _BACKOFF_INITIAL_SECONDS
        total_waited = 0.0
        while True:
            self._sleep_sync(backoff)
            total_waited += backoff
            sample = self._sample()
            if self._resume_ready(sample):
                logger.info(
                    "system_load_resume",
                    reason=reason,
                    waited_seconds=round(total_waited, 1),
                    cpu_percent=round(sample.cpu_percent, 1),
                    ram_percent=round(sample.ram_percent, 1),
                    disk_percent=round(sample.disk_percent, 1),
                )
                return sample
            backoff = self._next_backoff(backoff)


_GUARD: SystemLoadGuard | None = None


def get_system_load_guard() -> SystemLoadGuard:
    """Process-wide guard. Cheap; sampling happens per call, not on construction."""
    global _GUARD
    if _GUARD is None:
        _GUARD = SystemLoadGuard()
    return _GUARD


def reset_system_load_guard_for_tests() -> None:
    """Drop the cached guard so tests can install fakes via construction."""
    global _GUARD
    _GUARD = None
