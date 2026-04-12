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
    out = await repo.hh_vacancy_ids_with_success_or_employer_questions(
        1,
        9,
        ["111", "222", "333"],
    )

    assert out == {"111", "222"}
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_hh_vacancy_ids_with_success_or_employer_questions_empty_input():
    session = MagicMock()
    repo = HhApplicationAttemptRepository(session)
    assert await repo.hh_vacancy_ids_with_success_or_employer_questions(1, 9, []) == set()
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_latest_attempt_status_for_user_vacancy_returns_most_recent():
    session = MagicMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = "needs_employer_questions"
    session.execute = AsyncMock(return_value=result_mock)

    repo = HhApplicationAttemptRepository(session)
    assert (
        await repo.latest_attempt_status_for_user_vacancy(1, 9, "999")
        == "needs_employer_questions"
    )
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_user_has_any_attempt_for_hh_vacancy_scopes_by_hh_account():
    session = MagicMock()
    result_mock = MagicMock()
    result_mock.scalar_one.return_value = 1
    session.execute = AsyncMock(return_value=result_mock)

    repo = HhApplicationAttemptRepository(session)
    assert await repo.user_has_any_attempt_for_hh_vacancy(1, 9, "999") is True

    stmt = session.execute.await_args.args[0]
    assert "hh_application_attempts.hh_linked_account_id" in str(stmt)
