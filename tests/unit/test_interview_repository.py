"""Unit tests for InterviewRepository."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.repositories.interview import InterviewRepository


@pytest.mark.asyncio
async def test_update_company_review_persists_content():
    """update_company_review persists content to interview."""
    session = AsyncMock()
    mock_interview = MagicMock()
    mock_interview.id = 1

    mock_get_by_id = AsyncMock(return_value=mock_interview)
    mock_update = AsyncMock(return_value=mock_interview)

    with (
        patch.object(InterviewRepository, "get_by_id", mock_get_by_id),
        patch.object(InterviewRepository, "update", mock_update),
    ):
        repo = InterviewRepository(session)
        await repo.update_company_review(1, "Company review content")

    mock_get_by_id.assert_called_once_with(1)
    mock_update.assert_called_once_with(
        mock_interview, company_review="Company review content"
    )


@pytest.mark.asyncio
async def test_update_company_review_does_nothing_when_interview_not_found():
    """update_company_review does nothing when interview not found."""
    session = AsyncMock()
    mock_get_by_id = AsyncMock(return_value=None)
    mock_update = AsyncMock()

    with (
        patch.object(InterviewRepository, "get_by_id", mock_get_by_id),
        patch.object(InterviewRepository, "update", mock_update),
    ):
        repo = InterviewRepository(session)
        await repo.update_company_review(1, "Company review content")

    mock_get_by_id.assert_called_once_with(1)
    mock_update.assert_not_called()


@pytest.mark.asyncio
async def test_update_questions_to_ask_persists_content():
    """update_questions_to_ask persists content to interview."""
    session = AsyncMock()
    mock_interview = MagicMock()
    mock_interview.id = 1

    mock_get_by_id = AsyncMock(return_value=mock_interview)
    mock_update = AsyncMock(return_value=mock_interview)

    with (
        patch.object(InterviewRepository, "get_by_id", mock_get_by_id),
        patch.object(InterviewRepository, "update", mock_update),
    ):
        repo = InterviewRepository(session)
        await repo.update_questions_to_ask(1, "Q1: Tell me about yourself")

    mock_get_by_id.assert_called_once_with(1)
    mock_update.assert_called_once_with(
        mock_interview, questions_to_ask="Q1: Tell me about yourself"
    )
