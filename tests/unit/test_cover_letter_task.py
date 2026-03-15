"""Unit tests for cover letter generation task."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.worker.tasks.cover_letter import (
    _generate_cover_letter_async,
    _strip_agent_wrapper,
)


class TestStripAgentWrapper:
    def test_returns_empty_for_empty_input(self) -> None:
        assert _strip_agent_wrapper("") == ""

    def test_returns_whitespace_for_whitespace_only_input(self) -> None:
        assert _strip_agent_wrapper("   ").strip() == ""

    def test_strips_leading_intro_phrase(self) -> None:
        text = "Вот сопроводительное письмо.\n\nДобрый день!"
        assert "Добрый день" in _strip_agent_wrapper(text)

    def test_preserves_mogu_podgotovit_in_call_to_action(self) -> None:
        """Phrases like «Могу подготовить» are legitimate in cover letters (call to action)."""
        text = (
            "Добрый день! Я заинтересован в вакансии.\n\n"
            "Могу подготовить презентацию моих проектов."
        )
        result = _strip_agent_wrapper(text)
        assert "Могу подготовить презентацию" in result


@pytest.mark.asyncio
async def test_cover_letter_task_disabled_returns_early() -> None:
    task = MagicMock()
    task.check_enabled = AsyncMock(return_value=False)

    session = AsyncMock()
    session_factory = AsyncMock()
    session_factory.return_value.__aenter__.return_value = session
    session_factory.return_value.__aexit__.return_value = None

    result = await _generate_cover_letter_async(
        task,
        session_factory,
        user_id=1,
        vacancy_id=10,
        chat_id=123,
        message_id=456,
        locale="ru",
        cover_letter_style="professional",
    )

    assert result == {"status": "disabled"}
    task.check_enabled.assert_called_once()


@pytest.mark.asyncio
async def test_cover_letter_task_circuit_open_returns_early() -> None:
    task = MagicMock()
    task.check_enabled = AsyncMock(return_value=True)
    cb = MagicMock()
    cb.is_call_allowed.return_value = False
    task.load_circuit_breaker = AsyncMock(return_value=cb)

    session = AsyncMock()
    session_factory = AsyncMock()
    session_factory.return_value.__aenter__.return_value = session
    session_factory.return_value.__aexit__.return_value = None

    result = await _generate_cover_letter_async(
        task,
        session_factory,
        user_id=1,
        vacancy_id=10,
        chat_id=123,
        message_id=456,
        locale="ru",
        cover_letter_style="professional",
    )

    assert result == {"status": "circuit_open"}


@pytest.mark.asyncio
async def test_cover_letter_task_vacancy_not_found_returns_early() -> None:
    task = MagicMock()
    task.check_enabled = AsyncMock(return_value=True)
    cb = MagicMock()
    cb.is_call_allowed.return_value = True
    task.load_circuit_breaker = AsyncMock(return_value=cb)

    session = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    session_factory = MagicMock(return_value=ctx)

    with (
        patch(
            "src.repositories.task.CeleryTaskRepository"
        ) as mock_task_repo_cls,
        patch(
            "src.repositories.work_experience.WorkExperienceRepository"
        ) as mock_we_repo_cls,
        patch(
            "src.repositories.autoparse.AutoparsedVacancyRepository"
        ) as mock_vac_repo_cls,
    ):
        mock_task_repo = AsyncMock()
        mock_task_repo.get_by_idempotency_key = AsyncMock(return_value=None)
        mock_task_repo_cls.return_value = mock_task_repo

        mock_we_repo = AsyncMock()
        mock_we_repo.get_active_by_user = AsyncMock(return_value=[])
        mock_we_repo_cls.return_value = mock_we_repo

        mock_vac_repo = AsyncMock()
        mock_vac_repo.get_by_id = AsyncMock(return_value=None)
        mock_vac_repo_cls.return_value = mock_vac_repo

        result = await _generate_cover_letter_async(
            task,
            session_factory,
            user_id=1,
            vacancy_id=999,
            chat_id=123,
            message_id=456,
            locale="ru",
            cover_letter_style="professional",
        )

    assert result == {"status": "vacancy_not_found"}
