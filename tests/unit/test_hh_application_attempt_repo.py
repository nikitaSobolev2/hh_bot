"""Tests for HhApplicationAttemptRepository helpers."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.repositories.hh_application_attempt import HhApplicationAttemptRepository


@pytest.mark.asyncio
async def test_has_successful_apply_true() -> None:
    session = MagicMock()
    result = MagicMock()
    result.scalar_one.return_value = 1
    session.execute = AsyncMock(return_value=result)

    repo = HhApplicationAttemptRepository(session)
    assert await repo.has_successful_apply(1, "v1", "r1") is True


@pytest.mark.asyncio
async def test_has_successful_apply_false() -> None:
    session = MagicMock()
    result = MagicMock()
    result.scalar_one.return_value = 0
    session.execute = AsyncMock(return_value=result)

    repo = HhApplicationAttemptRepository(session)
    assert await repo.has_successful_apply(1, "v1", "r1") is False
