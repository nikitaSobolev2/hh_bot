"""Shared fixtures for all tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def make_vacancy():
    """Factory for minimal AutoparsedVacancy-like mock objects."""

    def _make(
        vacancy_id: int = 1,
        title: str = "Python Developer",
        url: str = "https://hh.ru/vacancy/1",
        company_name: str | None = "Acme Corp",
        salary: str | None = "200 000 руб.",
        compatibility_score: float | None = None,
        description: str = "Test description",
        raw_skills: list | None = None,
        work_experience: str | None = None,
        employment_type: str | None = None,
        work_schedule: str | None = None,
        working_hours: str | None = None,
        work_formats: str | None = None,
        ai_summary: str | None = None,
        ai_stack: list | None = None,
    ):
        from unittest.mock import MagicMock

        vacancy = MagicMock()
        vacancy.id = vacancy_id
        vacancy.title = title
        vacancy.url = url
        vacancy.company_name = company_name
        vacancy.salary = salary
        vacancy.compatibility_score = compatibility_score
        vacancy.description = description
        vacancy.raw_skills = raw_skills
        vacancy.work_experience = work_experience
        vacancy.employment_type = employment_type
        vacancy.work_schedule = work_schedule
        vacancy.working_hours = working_hours
        vacancy.work_formats = work_formats
        vacancy.ai_summary = ai_summary
        vacancy.ai_stack = ai_stack
        return vacancy

    return _make


@pytest.fixture
def make_feed_session():
    """Factory for minimal VacancyFeedSession-like mock objects."""

    def _make(
        session_id: int = 1,
        user_id: int = 42,
        company_id: int = 10,
        chat_id: int = 42,
        vacancy_ids: list | None = None,
        current_index: int = 0,
        liked_ids: list | None = None,
        disliked_ids: list | None = None,
        is_completed: bool = False,
    ):
        from unittest.mock import MagicMock

        feed_session = MagicMock()
        feed_session.id = session_id
        feed_session.user_id = user_id
        feed_session.autoparse_company_id = company_id
        feed_session.chat_id = chat_id
        feed_session.vacancy_ids = vacancy_ids if vacancy_ids is not None else [1, 2, 3]
        feed_session.current_index = current_index
        feed_session.liked_ids = liked_ids if liked_ids is not None else []
        feed_session.disliked_ids = disliked_ids if disliked_ids is not None else []
        feed_session.is_completed = is_completed
        return feed_session

    return _make


@pytest.fixture
def mock_session():
    """Minimal async SQLAlchemy session mock."""
    session = MagicMock()
    session.execute = AsyncMock()
    session.get = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session
