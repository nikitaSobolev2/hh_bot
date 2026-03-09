"""Unit tests for autoparse task helper functions."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.worker.tasks.autoparse import _build_user_profile, _resolve_cached_vacancy


class TestBuildUserProfile:
    def test_returns_custom_stack_when_set(self):
        ap_settings = {"tech_stack": ["Python", "Django"]}
        work_experiences = []

        stack, exp = _build_user_profile(ap_settings, work_experiences)

        assert stack == ["Python", "Django"]
        assert exp == ""

    def test_derives_stack_from_work_experiences_when_no_custom_stack(self):
        exp_entry = MagicMock()
        exp_entry.company_name = "Acme"
        exp_entry.stack = "Python, FastAPI"

        stack, exp = _build_user_profile({}, [exp_entry])

        assert "Python" in stack
        assert "FastAPI" in stack
        assert "Acme — Python, FastAPI" in exp

    def test_returns_empty_profile_when_no_data(self):
        stack, exp = _build_user_profile({}, [])

        assert stack == []
        assert exp == ""

    def test_formats_experience_from_multiple_entries(self):
        e1 = MagicMock()
        e1.company_name = "Alpha"
        e1.stack = "Go"
        e2 = MagicMock()
        e2.company_name = "Beta"
        e2.stack = "Rust"

        _, exp = _build_user_profile({}, [e1, e2])

        assert "Alpha — Go" in exp
        assert "Beta — Rust" in exp


class TestResolveCachedVacancy:
    @pytest.mark.asyncio
    async def test_returns_existing_autoparsed_when_found(self):
        existing = MagicMock()
        existing.raw_skills = ["Python"]
        existing.description = "desc"

        vacancy_repo = MagicMock()
        vacancy_repo.get_by_hh_id = AsyncMock(return_value=existing)
        parsed_vacancy_repo = MagicMock()
        parsed_vacancy_repo.get_by_hh_id = AsyncMock(return_value=None)

        vac = {"hh_vacancy_id": "123", "url": "http://hh.ru/vacancy/123", "cached": True}
        returned_vac, returned_existing = await _resolve_cached_vacancy(
            "123", vac, vacancy_repo, parsed_vacancy_repo
        )

        assert returned_existing is existing
        assert returned_vac is vac
        parsed_vacancy_repo.get_by_hh_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_parsed_vacancy_when_not_in_autoparsed(self):
        parsed_record = MagicMock()
        parsed_record.description = "full description"
        parsed_record.raw_skills = ["Python", "FastAPI"]

        vacancy_repo = MagicMock()
        vacancy_repo.get_by_hh_id = AsyncMock(return_value=None)
        parsed_vacancy_repo = MagicMock()
        parsed_vacancy_repo.get_by_hh_id = AsyncMock(return_value=parsed_record)

        vac = {"hh_vacancy_id": "456", "url": "http://hh.ru/vacancy/456", "cached": True}
        returned_vac, returned_existing = await _resolve_cached_vacancy(
            "456", vac, vacancy_repo, parsed_vacancy_repo
        )

        assert returned_existing is None
        assert returned_vac["description"] == "full description"
        assert returned_vac["raw_skills"] == ["Python", "FastAPI"]
        assert returned_vac["url"] == "http://hh.ru/vacancy/456"

    @pytest.mark.asyncio
    async def test_returns_original_vac_when_not_found_anywhere(self):
        vacancy_repo = MagicMock()
        vacancy_repo.get_by_hh_id = AsyncMock(return_value=None)
        parsed_vacancy_repo = MagicMock()
        parsed_vacancy_repo.get_by_hh_id = AsyncMock(return_value=None)

        vac = {"hh_vacancy_id": "789", "url": "http://hh.ru/vacancy/789", "cached": True}
        returned_vac, returned_existing = await _resolve_cached_vacancy(
            "789", vac, vacancy_repo, parsed_vacancy_repo
        )

        assert returned_existing is None
        assert returned_vac is vac

    @pytest.mark.asyncio
    async def test_uses_empty_strings_when_parsed_vacancy_fields_are_none(self):
        parsed_record = MagicMock()
        parsed_record.description = None
        parsed_record.raw_skills = None

        vacancy_repo = MagicMock()
        vacancy_repo.get_by_hh_id = AsyncMock(return_value=None)
        parsed_vacancy_repo = MagicMock()
        parsed_vacancy_repo.get_by_hh_id = AsyncMock(return_value=parsed_record)

        vac = {"hh_vacancy_id": "999", "cached": True}
        returned_vac, _ = await _resolve_cached_vacancy(
            "999", vac, vacancy_repo, parsed_vacancy_repo
        )

        assert returned_vac["description"] == ""
        assert returned_vac["raw_skills"] == []
