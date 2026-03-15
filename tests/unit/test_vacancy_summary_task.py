"""Unit tests for the vacancy summary (about-me) generation task."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_session_factory():
    session = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory, session


@pytest.fixture
def mock_task():
    task = MagicMock()
    task.check_enabled = AsyncMock(return_value=True)
    task.load_circuit_breaker = AsyncMock()
    task.is_already_completed = AsyncMock(return_value=False)
    task.mark_completed = AsyncMock()
    task.create_bot = MagicMock(return_value=AsyncMock())
    task.notify_user = AsyncMock()

    cb = MagicMock()
    cb.is_call_allowed = MagicMock(return_value=True)
    cb.record_success = MagicMock()
    cb.record_failure = MagicMock()
    task.load_circuit_breaker.return_value = cb

    return task, cb


class TestVacancySummaryTaskGuards:
    @pytest.mark.asyncio
    async def test_returns_disabled_when_feature_flag_off(self, mock_session_factory, mock_task):
        from src.worker.tasks.vacancy_summary import _generate_summary_async

        factory, _ = mock_session_factory
        task, _ = mock_task
        task.check_enabled.return_value = False

        result = await _generate_summary_async(
            task, factory, 1, 1, None, None, None, None, 100, 200, "ru"
        )
        assert result["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_returns_circuit_open_when_breaker_open(self, mock_session_factory, mock_task):
        from src.worker.tasks.vacancy_summary import _generate_summary_async

        factory, _ = mock_session_factory
        task, cb = mock_task
        cb.is_call_allowed.return_value = False

        result = await _generate_summary_async(
            task, factory, 1, 1, None, None, None, None, 100, 200, "ru"
        )
        assert result["status"] == "circuit_open"

    @pytest.mark.asyncio
    async def test_returns_already_completed_on_duplicate(self, mock_session_factory, mock_task):
        from src.worker.tasks.vacancy_summary import _generate_summary_async

        factory, _ = mock_session_factory
        task, _ = mock_task
        task.is_already_completed.return_value = True

        result = await _generate_summary_async(
            task, factory, 1, 1, None, None, None, None, 100, 200, "ru"
        )
        assert result["status"] == "already_completed"


class TestVacancySummaryIdempotencyKey:
    """Verify idempotency key is constructed correctly."""

    @pytest.mark.asyncio
    async def test_idempotency_key_includes_summary_id(self, mock_session_factory, mock_task):
        from src.worker.tasks.vacancy_summary import _generate_summary_async

        factory, _ = mock_session_factory
        task, _ = mock_task
        task.is_already_completed.return_value = True

        await _generate_summary_async(
            task,
            factory,
            summary_id=42,
            user_id=1,
            excluded_industries=None,
            location=None,
            remote_preference=None,
            additional_notes=None,
            chat_id=100,
            message_id=200,
            locale="ru",
        )

        call_args = task.is_already_completed.call_args[0]
        assert "42" in call_args[0]


class TestStripAgentWrapper:
    """Verify _strip_agent_wrapper removes intro/outro, keeps only summary content."""

    def test_strips_leading_intro_and_trailing_outro(self):
        from src.worker.tasks.vacancy_summary import _strip_agent_wrapper

        raw = (
            "Вот профессиональный текст «О себе» для вашего резюме, составленный на основе данных:\n\n"
            "---\n\n"
            "Я Senior Fullstack разработчик с 5-летним опытом.\n\n"
            "🔥 Как достигаю результата\n"
            "Строю архитектуру.\n\n"
            "---\n\n"
            "Если хотите, я могу подготовить ещё более «продающий» вариант под LinkedIn. "
            "Хотите, чтобы я так сделал?"
        )
        result = _strip_agent_wrapper(raw)
        assert "Вот профессиональный" not in result
        assert "Если хотите" not in result
        assert "Хотите, чтобы" not in result
        assert result.startswith("Я Senior")
        assert "🔥 Как достигаю" in result

    def test_preserves_clean_summary_unchanged(self):
        from src.worker.tasks.vacancy_summary import _strip_agent_wrapper

        clean = "Я Senior разработчик.\n\n🔥 Как достигаю результата\nСтрою архитектуру."
        assert _strip_agent_wrapper(clean) == clean

    def test_strips_only_outro_when_no_intro(self):
        from src.worker.tasks.vacancy_summary import _strip_agent_wrapper

        raw = "Я Senior разработчик.\n\nЕсли хотите, могу подготовить вариант под LinkedIn."
        result = _strip_agent_wrapper(raw)
        assert result == "Я Senior разработчик."
