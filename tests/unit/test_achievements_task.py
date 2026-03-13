"""Unit tests for the achievements generation Celery task."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_session_factory():
    """Return a mock async session factory."""
    session = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory, session


@pytest.fixture
def mock_task():
    """Return a mock HHBotTask instance with stubs for shared helpers."""
    task = MagicMock()
    task.check_enabled = AsyncMock(return_value=True)
    task.load_circuit_breaker = AsyncMock()
    task.is_already_completed = AsyncMock(return_value=False)
    task.create_bot = MagicMock(return_value=AsyncMock())
    task.notify_user = AsyncMock()

    cb = MagicMock()
    cb.is_call_allowed = MagicMock(return_value=True)
    cb.record_success = MagicMock()
    cb.record_failure = MagicMock()
    task.load_circuit_breaker.return_value = cb

    return task, cb


class TestAchievementsTaskDisabled:
    @pytest.mark.asyncio
    async def test_returns_disabled_when_feature_flag_is_off(self, mock_session_factory, mock_task):
        from src.worker.tasks.achievements import _generate_achievements_async

        factory, _ = mock_session_factory
        task, _ = mock_task
        task.check_enabled.return_value = False

        result = await _generate_achievements_async(task, factory, 1, 100, 200, "ru")
        assert result["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_returns_circuit_open_when_breaker_open(self, mock_session_factory, mock_task):
        from src.worker.tasks.achievements import _generate_achievements_async

        factory, _ = mock_session_factory
        task, cb = mock_task
        cb.is_call_allowed.return_value = False

        result = await _generate_achievements_async(task, factory, 1, 100, 200, "ru")
        assert result["status"] == "circuit_open"

    @pytest.mark.asyncio
    async def test_returns_already_completed_on_duplicate(self, mock_session_factory, mock_task):
        from src.worker.tasks.achievements import _generate_achievements_async

        factory, _ = mock_session_factory
        task, _ = mock_task
        task.is_already_completed.return_value = True

        result = await _generate_achievements_async(task, factory, 1, 100, 200, "ru")
        assert result["status"] == "already_completed"


class TestAchievementsTaskParsing:
    def test_parse_achievement_blocks_parses_single_block(self):
        from src.worker.tasks.achievements import _parse_achievement_blocks

        text = "[AchStart]:Google\nBuilt a search engine\n[AchEnd]:Google"
        result = _parse_achievement_blocks(text)
        assert result == {"Google": "Built a search engine"}

    def test_parse_achievement_blocks_strips_whitespace_from_company_name(self):
        from src.worker.tasks.achievements import _parse_achievement_blocks

        text = "[AchStart]: Trimmed Corp \nSome text\n[AchEnd]: Trimmed Corp "
        result = _parse_achievement_blocks(text)
        assert "Trimmed Corp" in result

    def test_parse_achievement_blocks_handles_empty_content(self):
        from src.worker.tasks.achievements import _parse_achievement_blocks

        text = "[AchStart]:Acme\n\n[AchEnd]:Acme"
        result = _parse_achievement_blocks(text)
        assert result["Acme"] == ""

    def test_parse_achievement_blocks_returns_empty_dict_for_no_blocks(self):
        from src.worker.tasks.achievements import _parse_achievement_blocks

        result = _parse_achievement_blocks("Some random text without blocks")
        assert result == {}

    def test_parse_achievement_blocks_handles_multiple_companies(self):
        from src.worker.tasks.achievements import _parse_achievement_blocks

        text = (
            "[AchStart]:Alpha\nAlpha achievement\n[AchEnd]:Alpha\n"
            "[AchStart]:Beta\nBeta achievement\n[AchEnd]:Beta"
        )
        result = _parse_achievement_blocks(text)
        assert len(result) == 2
        assert result["Alpha"] == "Alpha achievement"
        assert result["Beta"] == "Beta achievement"


class TestAchievementsTaskGetStack:
    def test_get_stack_returns_work_experience_stack(self):
        from src.worker.tasks.achievements import _get_stack

        item = MagicMock()
        item.work_experience = MagicMock()
        item.work_experience.stack = "Python, Django"
        assert _get_stack(item) == "Python, Django"

    def test_get_stack_returns_empty_when_no_work_experience(self):
        from src.worker.tasks.achievements import _get_stack

        item = MagicMock()
        item.work_experience = None
        assert _get_stack(item) == ""

    def test_get_stack_returns_empty_when_stack_is_none(self):
        from src.worker.tasks.achievements import _get_stack

        item = MagicMock()
        item.work_experience = MagicMock()
        item.work_experience.stack = None
        assert _get_stack(item) == ""
