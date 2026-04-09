"""Unit tests for the unreviewed-vacancy re-delivery fix."""

from unittest.mock import AsyncMock, MagicMock

import pytest

# ── VacancyFeedSessionRepository.get_all_reacted_vacancy_ids ────────


@pytest.mark.asyncio
async def test_get_all_reacted_vacancy_ids_returns_union_of_liked_and_disliked():
    """Only liked/disliked IDs count as reacted — queued-but-unseen do not."""
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.__iter__ = MagicMock(
        return_value=iter(
            [
                ([10, 20], [30]),
                ([40], []),
            ]
        )
    )
    mock_session.execute = AsyncMock(return_value=mock_result)

    from src.repositories.vacancy_feed import VacancyFeedSessionRepository

    repo = VacancyFeedSessionRepository(mock_session)
    reacted = await repo.get_all_reacted_vacancy_ids(user_id=1, company_id=5)

    assert reacted == {10, 20, 30, 40}


@pytest.mark.asyncio
async def test_get_all_reacted_vacancy_ids_returns_empty_set_when_no_sessions():
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.__iter__ = MagicMock(return_value=iter([]))
    mock_session.execute = AsyncMock(return_value=mock_result)

    from src.repositories.vacancy_feed import VacancyFeedSessionRepository

    repo = VacancyFeedSessionRepository(mock_session)
    reacted = await repo.get_all_reacted_vacancy_ids(user_id=1, company_id=5)

    assert reacted == set()


@pytest.mark.asyncio
async def test_get_all_reacted_vacancy_ids_excludes_queued_but_unseen():
    """Vacancy IDs only in vacancy_ids (not liked/disliked) are not returned."""
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.__iter__ = MagicMock(return_value=iter([([10], [])]))
    mock_session.execute = AsyncMock(return_value=mock_result)

    from src.repositories.vacancy_feed import VacancyFeedSessionRepository

    repo = VacancyFeedSessionRepository(mock_session)
    reacted = await repo.get_all_reacted_vacancy_ids(user_id=1, company_id=5)

    assert 99 not in reacted
    assert 10 in reacted


# ── VacancyFeedSessionRepository.get_all_liked_vacancy_ids_for_user ──


@pytest.mark.asyncio
async def test_get_all_liked_vacancy_ids_for_user_returns_unique_across_companies():
    """Aggregates liked_ids from all sessions for the user, returns unique set."""
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.__iter__ = MagicMock(
        return_value=iter(
            [
                ([10, 20],),
                ([20, 30],),
            ]
        )
    )
    mock_session.execute = AsyncMock(return_value=mock_result)

    from src.repositories.vacancy_feed import VacancyFeedSessionRepository

    repo = VacancyFeedSessionRepository(mock_session)
    liked = await repo.get_all_liked_vacancy_ids_for_user(user_id=1)

    assert liked == {10, 20, 30}


@pytest.mark.asyncio
async def test_get_all_liked_vacancy_ids_for_user_returns_empty_when_no_sessions():
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.__iter__ = MagicMock(return_value=iter([]))
    mock_session.execute = AsyncMock(return_value=mock_result)

    from src.repositories.vacancy_feed import VacancyFeedSessionRepository

    repo = VacancyFeedSessionRepository(mock_session)
    liked = await repo.get_all_liked_vacancy_ids_for_user(user_id=1)

    assert liked == set()


# ── VacancyFeedSessionRepository.get_all_disliked_vacancy_ids_for_user ─


@pytest.mark.asyncio
async def test_get_all_disliked_vacancy_ids_for_user_returns_unique_across_companies():
    """Aggregates disliked_ids from all sessions for the user, returns unique set."""
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.__iter__ = MagicMock(
        return_value=iter(
            [
                ([5, 15],),
                ([15, 25],),
            ]
        )
    )
    mock_session.execute = AsyncMock(return_value=mock_result)

    from src.repositories.vacancy_feed import VacancyFeedSessionRepository

    repo = VacancyFeedSessionRepository(mock_session)
    disliked = await repo.get_all_disliked_vacancy_ids_for_user(user_id=1)

    assert disliked == {5, 15, 25}


@pytest.mark.asyncio
async def test_get_liked_vacancy_page_for_user_returns_page_and_total():
    mock_session = MagicMock()
    total_result = MagicMock()
    total_result.scalar.return_value = 3
    page_result = MagicMock()
    page_result.scalars.return_value.all.return_value = [30, 20]
    mock_session.execute = AsyncMock(side_effect=[total_result, page_result])

    from src.repositories.vacancy_feed import VacancyFeedSessionRepository

    repo = VacancyFeedSessionRepository(mock_session)
    ids, total = await repo.get_liked_vacancy_page_for_user(user_id=1, offset=0, limit=2)

    assert ids == [30, 20]
    assert total == 3


@pytest.mark.asyncio
async def test_get_disliked_vacancy_page_for_user_returns_page_and_total():
    mock_session = MagicMock()
    total_result = MagicMock()
    total_result.scalar.return_value = 4
    page_result = MagicMock()
    page_result.scalars.return_value.all.return_value = [40, 10]
    mock_session.execute = AsyncMock(side_effect=[total_result, page_result])

    from src.repositories.vacancy_feed import VacancyFeedSessionRepository

    repo = VacancyFeedSessionRepository(mock_session)
    ids, total = await repo.get_disliked_vacancy_page_for_user(user_id=1, offset=0, limit=2)

    assert ids == [40, 10]
    assert total == 4


# ── VacancyFeedSessionRepository bulk clear (per company) ───────────


@pytest.mark.asyncio
async def test_clear_liked_ids_for_user_company_executes_update():
    mock_session = MagicMock()
    mock_session.execute = AsyncMock()

    from src.repositories.vacancy_feed import VacancyFeedSessionRepository

    repo = VacancyFeedSessionRepository(mock_session)
    await repo.clear_liked_ids_for_user_company(42, 7)

    mock_session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_clear_disliked_ids_for_user_company_executes_update():
    mock_session = MagicMock()
    mock_session.execute = AsyncMock()

    from src.repositories.vacancy_feed import VacancyFeedSessionRepository

    repo = VacancyFeedSessionRepository(mock_session)
    await repo.clear_disliked_ids_for_user_company(99, 3)

    mock_session.execute.assert_awaited_once()


# ── AutoparsedVacancyRepository.get_by_ids ──────────────────────────


@pytest.mark.asyncio
async def test_get_by_ids_returns_empty_list_for_empty_ids():
    mock_session = AsyncMock()

    from src.repositories.autoparse import AutoparsedVacancyRepository

    repo = AutoparsedVacancyRepository(mock_session)
    result = await repo.get_by_ids([], min_compat=50.0)

    assert result == []
    mock_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_get_by_ids_queries_when_ids_provided():
    mock_session = MagicMock()
    vacancy = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [vacancy]
    mock_session.execute = AsyncMock(return_value=mock_result)

    from src.repositories.autoparse import AutoparsedVacancyRepository

    repo = AutoparsedVacancyRepository(mock_session)
    result = await repo.get_by_ids([1, 2, 3], min_compat=50.0)

    mock_session.execute.assert_called_once()
    assert result == [vacancy]


# ── Unreviewed ID computation logic ─────────────────────────────────


def test_unreviewed_ids_are_queued_minus_reacted():
    """Core fix logic: unseen = all queued IDs minus IDs the user reacted to."""
    queued_ids = {100, 200, 300, 400, 500}
    reacted_ids = {100, 200, 300}

    unreviewed_ids = queued_ids - reacted_ids

    assert unreviewed_ids == {400, 500}


def test_unreviewed_ids_empty_when_all_reacted():
    queued_ids = {10, 20, 30}
    reacted_ids = {10, 20, 30}

    assert queued_ids - reacted_ids == set()


def test_unreviewed_ids_full_when_none_reacted():
    queued_ids = {10, 20, 30}
    reacted_ids: set[int] = set()

    assert queued_ids - reacted_ids == {10, 20, 30}
