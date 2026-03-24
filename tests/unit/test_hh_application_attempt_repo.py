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


@pytest.mark.asyncio
async def test_hh_vacancy_ids_with_successful_apply_empty_skips_query() -> None:
    session = MagicMock()
    repo = HhApplicationAttemptRepository(session)
    assert await repo.hh_vacancy_ids_with_successful_apply(1, "r1", []) == set()
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_hh_vacancy_ids_with_successful_apply_returns_set() -> None:
    session = MagicMock()
    result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = ["111", "222"]
    result.scalars.return_value = mock_scalars
    session.execute = AsyncMock(return_value=result)

    repo = HhApplicationAttemptRepository(session)
    out = await repo.hh_vacancy_ids_with_successful_apply(1, "r1", ["111", "222", "333"])
    assert out == {"111", "222"}
