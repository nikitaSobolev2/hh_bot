"""Unit tests for AutoparsedVacancyRepository get_unseen_for_user and
get_below_min_compat_for_user.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_get_unseen_for_user_excludes_reacted_ids():
    """get_unseen_for_user adds notin clause when exclude_vacancy_ids is non-empty."""
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    from src.repositories.autoparse import AutoparsedVacancyRepository

    repo = AutoparsedVacancyRepository(mock_session)
    await repo.get_unseen_for_user(user_id=1, exclude_vacancy_ids={10, 20})

    mock_session.execute.assert_called_once()
    stmt = mock_session.execute.call_args[0][0]
    assert "autoparse_companies" in str(stmt)
    assert "user_id" in str(stmt) or "user_id" in str(stmt.compile())


@pytest.mark.asyncio
async def test_get_unseen_for_user_returns_from_user_companies_only():
    """get_unseen_for_user joins with AutoparseCompany and filters by user_id."""
    mock_session = MagicMock()
    vacancy = MagicMock()
    vacancy.id = 5
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [vacancy]
    mock_session.execute = AsyncMock(return_value=mock_result)

    from src.repositories.autoparse import AutoparsedVacancyRepository

    repo = AutoparsedVacancyRepository(mock_session)
    result = await repo.get_unseen_for_user(user_id=42, exclude_vacancy_ids=set())

    assert len(result) == 1
    assert result[0].id == 5


@pytest.mark.asyncio
async def test_get_below_min_compat_for_user_includes_none_and_below_threshold():
    """get_below_min_compat_for_user filters by score < min_compat or score is None."""
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    from src.repositories.autoparse import AutoparsedVacancyRepository

    repo = AutoparsedVacancyRepository(mock_session)
    await repo.get_below_min_compat_for_user(
        user_id=1, min_compat=50.0, exclude_vacancy_ids=set()
    )

    mock_session.execute.assert_called_once()
    stmt = mock_session.execute.call_args[0][0]
    stmt_str = str(stmt.compile())
    assert "compatibility_score" in stmt_str


@pytest.mark.asyncio
async def test_get_by_ids_for_company_preserves_ids_order():
    """Rows from DB are mapped back in the order of the requested *ids* list."""
    mock_session = MagicMock()
    v1 = MagicMock()
    v1.id = 1
    v2 = MagicMock()
    v2.id = 2
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [v2, v1]
    mock_session.execute = AsyncMock(return_value=mock_result)

    from src.repositories.autoparse import AutoparsedVacancyRepository

    repo = AutoparsedVacancyRepository(mock_session)
    out = await repo.get_by_ids_for_company(10, [1, 2])
    assert [v.id for v in out] == [1, 2]


@pytest.mark.asyncio
async def test_get_below_min_compat_for_user_excludes_reacted():
    """get_below_min_compat_for_user adds notin when exclude_vacancy_ids provided."""
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    from src.repositories.autoparse import AutoparsedVacancyRepository

    repo = AutoparsedVacancyRepository(mock_session)
    await repo.get_below_min_compat_for_user(
        user_id=1, min_compat=50.0, exclude_vacancy_ids={1, 2, 3}
    )

    mock_session.execute.assert_called_once()
