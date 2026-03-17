"""Unit tests for CoverLetterVacancyRepository."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.models.cover_letter_vacancy import CoverLetterVacancy
from src.repositories.cover_letter_vacancy import CoverLetterVacancyRepository


@pytest.mark.asyncio
async def test_create_or_update_from_api_creates_when_not_exists() -> None:
    session = AsyncMock()
    created = CoverLetterVacancy(
        id=1,
        user_id=1,
        hh_vacancy_id="123",
        url="https://hh.ru/vacancy/123",
        title="Python Developer",
        company_name="Acme",
        description="Job desc",
        raw_skills=["Python", "Django"],
    )
    repo = CoverLetterVacancyRepository(session)
    repo.get_by_hh_id = AsyncMock(return_value=None)
    repo.create = AsyncMock(return_value=created)

    result = await repo.create_or_update_from_api(
        user_id=1,
        hh_vacancy_id="123",
        url="https://hh.ru/vacancy/123",
        title="Python Developer",
        company_name="Acme",
        description="Job desc",
        raw_skills=["Python", "Django"],
    )

    repo.create.assert_called_once_with(
        user_id=1,
        hh_vacancy_id="123",
        url="https://hh.ru/vacancy/123",
        title="Python Developer",
        company_name="Acme",
        description="Job desc",
        raw_skills=["Python", "Django"],
    )
    assert result == created


@pytest.mark.asyncio
async def test_create_or_update_from_api_updates_when_exists() -> None:
    session = AsyncMock()
    existing = CoverLetterVacancy(
        id=1,
        user_id=1,
        hh_vacancy_id="123",
        url="https://hh.ru/vacancy/123",
        title="Old Title",
        company_name="Old Co",
        description="Old desc",
        raw_skills=None,
    )
    repo = CoverLetterVacancyRepository(session)
    repo.get_by_hh_id = AsyncMock(return_value=existing)
    repo.update = AsyncMock(return_value=existing)

    result = await repo.create_or_update_from_api(
        user_id=1,
        hh_vacancy_id="123",
        url="https://hh.ru/vacancy/123",
        title="New Title",
        company_name="New Co",
        description="New desc",
        raw_skills=["Python"],
    )

    repo.update.assert_called_once()
    assert result == existing


@pytest.mark.asyncio
async def test_get_by_hh_id_returns_existing() -> None:
    session = AsyncMock()
    existing = CoverLetterVacancy(
        id=1,
        user_id=1,
        hh_vacancy_id="123",
        url="https://hh.ru/vacancy/123",
        title="Title",
        company_name="Co",
        description="Desc",
        raw_skills=None,
    )
    repo = CoverLetterVacancyRepository(session)
    repo.get_by_hh_id = AsyncMock(return_value=existing)

    result = await repo.get_by_hh_id(user_id=1, hh_vacancy_id="123")
    assert result == existing
    assert result.title == "Title"
