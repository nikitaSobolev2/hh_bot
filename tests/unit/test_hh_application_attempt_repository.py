"""Unit tests for HhApplicationAttemptRepository skip helpers."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.repositories.hh_application_attempt import HhApplicationAttemptRepository


@pytest.mark.asyncio
async def test_hh_vacancy_ids_with_success_or_employer_questions_returns_both_statuses():
    session = MagicMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = ["111", "222"]
    session.execute = AsyncMock(return_value=result_mock)

    repo = HhApplicationAttemptRepository(session)
    out = await repo.hh_vacancy_ids_with_success_or_employer_questions(1, ["111", "222", "333"])

    assert out == {"111", "222"}
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_hh_vacancy_ids_with_success_or_employer_questions_empty_input():
    session = MagicMock()
    repo = HhApplicationAttemptRepository(session)
    assert await repo.hh_vacancy_ids_with_success_or_employer_questions(1, []) == set()
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_latest_attempt_status_for_user_vacancy_returns_most_recent():
    session = MagicMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = "needs_employer_questions"
    session.execute = AsyncMock(return_value=result_mock)

    repo = HhApplicationAttemptRepository(session)
    assert await repo.latest_attempt_status_for_user_vacancy(1, "999") == "needs_employer_questions"
    session.execute.assert_called_once()
