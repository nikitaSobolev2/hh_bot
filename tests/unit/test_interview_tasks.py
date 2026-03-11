"""Unit tests for interview Celery tasks.

Covers: success path, circuit-breaker open path, idempotency skip path,
and disabled-setting path for both analyze and generate_flow tasks.

All imports used inside the async implementations are patched at their
*source* module paths (where the name is defined), not at the task module
(where the names are local, i.e. not module-level attributes).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_session_factory(session: AsyncMock):
    """Return a callable that always yields the given mock session."""

    @asynccontextmanager
    async def _factory():
        yield session

    return _factory


def _make_fake_task(retries: int = 0, max_retries: int = 2) -> MagicMock:
    task = MagicMock()
    task.request.retries = retries
    task.max_retries = max_retries
    return task


def _make_interview(ai_summary: str | None = None) -> MagicMock:
    interview = MagicMock()
    interview.id = 1
    interview.vacancy_title = "Senior Python Developer"
    interview.vacancy_description = "Python, FastAPI"
    interview.company_name = "Acme Corp"
    interview.experience_level = "3-6"
    interview.hh_vacancy_url = "https://hh.ru/vacancy/123"
    interview.ai_summary = ai_summary
    interview.questions = [
        MagicMock(question="Tell me about yourself", user_answer="I am a developer"),
    ]
    interview.improvements = []
    return interview


def _make_improvement(improvement_flow: str | None = None) -> MagicMock:
    improvement = MagicMock()
    improvement.id = 10
    improvement.interview_id = 1
    improvement.technology_title = "Python"
    improvement.summary = "Needs to review async patterns"
    improvement.improvement_flow = improvement_flow
    return improvement


def _make_bot_mock() -> MagicMock:
    bot = AsyncMock()
    bot.session = AsyncMock()
    return bot


# ── analyze_interview_task ────────────────────────────────────────────────────


class TestAnalyzeInterviewTask:
    @pytest.mark.asyncio
    async def test_disabled_setting_returns_disabled(self):
        from src.worker.tasks.interviews import _analyze_interview_async

        session = AsyncMock()
        sf = _make_session_factory(session)

        with patch(
            "src.worker.tasks.interviews._load_circuit_breaker_config",
            new=AsyncMock(return_value=(False, 5, 60)),
        ):
            result = await _analyze_interview_async(sf, _make_fake_task(), 1, 100, 200, "ru", None)

        assert result == {"status": "disabled"}

    @pytest.mark.asyncio
    async def test_circuit_open_returns_circuit_open(self):
        from src.worker.tasks.interviews import _analyze_interview_async

        session = AsyncMock()
        sf = _make_session_factory(session)

        mock_cb = MagicMock()
        mock_cb.is_call_allowed.return_value = False

        with (
            patch(
                "src.worker.tasks.interviews._load_circuit_breaker_config",
                new=AsyncMock(return_value=(True, 5, 60)),
            ),
            patch("src.worker.circuit_breaker.CircuitBreaker", return_value=mock_cb),
        ):
            result = await _analyze_interview_async(sf, _make_fake_task(), 1, 100, 200, "ru", None)

        assert result == {"status": "circuit_open"}

    @pytest.mark.asyncio
    async def test_idempotency_skips_when_already_analyzed(self):
        from src.worker.tasks.interviews import _analyze_interview_async

        interview = _make_interview(ai_summary="existing summary")
        mock_repo = AsyncMock()
        mock_repo.get_with_relations = AsyncMock(return_value=interview)
        mock_interview_repo_cls = MagicMock(return_value=mock_repo)

        mock_cb = MagicMock()
        mock_cb.is_call_allowed.return_value = True

        mock_bot = _make_bot_mock()

        session = AsyncMock()
        sf = _make_session_factory(session)

        with (
            patch(
                "src.worker.tasks.interviews._load_circuit_breaker_config",
                new=AsyncMock(return_value=(True, 5, 60)),
            ),
            patch("src.worker.circuit_breaker.CircuitBreaker", return_value=mock_cb),
            patch("aiogram.Bot", return_value=mock_bot),
            patch("aiogram.client.default.DefaultBotProperties"),
            patch("src.config.settings", bot_token="fake_token"),
            patch("src.repositories.interview.InterviewRepository", mock_interview_repo_cls),
        ):
            result = await _analyze_interview_async(sf, _make_fake_task(), 1, 100, 200, "ru", None)

        assert result == {"status": "already_completed"}
        mock_bot.session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_success_calls_analyze_and_edits_message(self):
        from src.worker.tasks.interviews import _analyze_interview_async

        interview = _make_interview(ai_summary=None)
        mock_improvement = _make_improvement()

        mock_interview_repo = AsyncMock()
        mock_interview_repo.get_with_relations = AsyncMock(return_value=interview)
        mock_interview_repo_cls = MagicMock(return_value=mock_interview_repo)

        mock_cb = MagicMock()
        mock_cb.is_call_allowed.return_value = True

        mock_bot = _make_bot_mock()

        mock_analyze = AsyncMock(return_value=("AI summary text", [mock_improvement]))
        mock_keyboard = MagicMock()
        mock_keyboard_fn = MagicMock(return_value=mock_keyboard)

        session = AsyncMock()
        sf = _make_session_factory(session)

        with (
            patch(
                "src.worker.tasks.interviews._load_circuit_breaker_config",
                new=AsyncMock(return_value=(True, 5, 60)),
            ),
            patch("src.worker.circuit_breaker.CircuitBreaker", return_value=mock_cb),
            patch("aiogram.Bot", return_value=mock_bot),
            patch("aiogram.client.default.DefaultBotProperties"),
            patch("src.config.settings", bot_token="fake_token"),
            patch("src.repositories.interview.InterviewRepository", mock_interview_repo_cls),
            patch("src.bot.modules.interviews.services.analyze_and_save", mock_analyze),
            patch(
                "src.bot.modules.interviews.keyboards.interview_detail_keyboard",
                mock_keyboard_fn,
            ),
            patch(
                "src.bot.modules.interviews.services.format_vacancy_header",
                return_value="<b>Senior Python Developer</b>",
            ),
            patch("src.core.i18n.get_text", side_effect=lambda key, locale, **kw: key),
        ):
            result = await _analyze_interview_async(
                sf, _make_fake_task(), 1, 100, 200, "ru", "I want to improve Python"
            )

        assert result == {"status": "completed", "interview_id": 1}
        mock_bot.edit_message_text.assert_called_once()
        mock_cb.record_success.assert_called_once()
        mock_bot.session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_notifies_user_and_retries_on_final_attempt(self):
        from src.worker.tasks.interviews import _analyze_interview_async

        interview = _make_interview(ai_summary=None)
        mock_interview_repo = AsyncMock()
        mock_interview_repo.get_with_relations = AsyncMock(return_value=interview)
        mock_interview_repo_cls = MagicMock(return_value=mock_interview_repo)

        mock_cb = MagicMock()
        mock_cb.is_call_allowed.return_value = True

        mock_bot = _make_bot_mock()

        task = _make_fake_task(retries=2, max_retries=2)
        task.retry.side_effect = RuntimeError("max retries exceeded")

        session = AsyncMock()
        sf = _make_session_factory(session)

        with (
            patch(
                "src.worker.tasks.interviews._load_circuit_breaker_config",
                new=AsyncMock(return_value=(True, 5, 60)),
            ),
            patch("src.worker.circuit_breaker.CircuitBreaker", return_value=mock_cb),
            patch("aiogram.Bot", return_value=mock_bot),
            patch("aiogram.client.default.DefaultBotProperties"),
            patch("src.config.settings", bot_token="fake_token"),
            patch("src.repositories.interview.InterviewRepository", mock_interview_repo_cls),
            patch(
                "src.bot.modules.interviews.services.analyze_and_save",
                new=AsyncMock(side_effect=ValueError("AI service down")),
            ),
            patch("src.core.i18n.get_text", side_effect=lambda key, locale, **kw: key),
            pytest.raises(RuntimeError, match="max retries exceeded"),
        ):
            await _analyze_interview_async(sf, task, 1, 100, 200, "ru", None)

        task.retry.assert_called_once()
        mock_bot.edit_message_text.assert_called_once()
        call_kwargs = mock_bot.edit_message_text.call_args.kwargs
        assert call_kwargs["text"] == "iv-analysis-failed"

    @pytest.mark.asyncio
    async def test_retries_without_notifying_on_non_final_attempt(self):
        from src.worker.tasks.interviews import _analyze_interview_async

        interview = _make_interview(ai_summary=None)
        mock_interview_repo = AsyncMock()
        mock_interview_repo.get_with_relations = AsyncMock(return_value=interview)
        mock_interview_repo_cls = MagicMock(return_value=mock_interview_repo)

        mock_cb = MagicMock()
        mock_cb.is_call_allowed.return_value = True

        mock_bot = _make_bot_mock()

        task = _make_fake_task(retries=0, max_retries=2)
        task.retry.side_effect = RuntimeError("retry scheduled")

        session = AsyncMock()
        sf = _make_session_factory(session)

        with (
            patch(
                "src.worker.tasks.interviews._load_circuit_breaker_config",
                new=AsyncMock(return_value=(True, 5, 60)),
            ),
            patch("src.worker.circuit_breaker.CircuitBreaker", return_value=mock_cb),
            patch("aiogram.Bot", return_value=mock_bot),
            patch("aiogram.client.default.DefaultBotProperties"),
            patch("src.config.settings", bot_token="fake_token"),
            patch("src.repositories.interview.InterviewRepository", mock_interview_repo_cls),
            patch(
                "src.bot.modules.interviews.services.analyze_and_save",
                new=AsyncMock(side_effect=ValueError("transient error")),
            ),
            patch("src.core.i18n.get_text", side_effect=lambda key, locale, **kw: key),
            pytest.raises(RuntimeError, match="retry scheduled"),
        ):
            await _analyze_interview_async(sf, task, 1, 100, 200, "ru", None)

        task.retry.assert_called_once()
        mock_bot.edit_message_text.assert_not_called()


# ── generate_improvement_flow_task ────────────────────────────────────────────


class TestGenerateImprovementFlowTask:
    @pytest.mark.asyncio
    async def test_disabled_setting_returns_disabled(self):
        from src.worker.tasks.interviews import _generate_flow_async

        session = AsyncMock()
        sf = _make_session_factory(session)

        with patch(
            "src.worker.tasks.interviews._load_circuit_breaker_config",
            new=AsyncMock(return_value=(False, 5, 60)),
        ):
            result = await _generate_flow_async(sf, _make_fake_task(), 10, 1, 100, 200, "ru")

        assert result == {"status": "disabled"}

    @pytest.mark.asyncio
    async def test_circuit_open_returns_circuit_open(self):
        from src.worker.tasks.interviews import _generate_flow_async

        session = AsyncMock()
        sf = _make_session_factory(session)

        mock_cb = MagicMock()
        mock_cb.is_call_allowed.return_value = False

        with (
            patch(
                "src.worker.tasks.interviews._load_circuit_breaker_config",
                new=AsyncMock(return_value=(True, 5, 60)),
            ),
            patch("src.worker.circuit_breaker.CircuitBreaker", return_value=mock_cb),
        ):
            result = await _generate_flow_async(sf, _make_fake_task(), 10, 1, 100, 200, "ru")

        assert result == {"status": "circuit_open"}

    @pytest.mark.asyncio
    async def test_idempotency_skips_when_flow_already_generated(self):
        from src.worker.tasks.interviews import _generate_flow_async

        improvement = _make_improvement(improvement_flow="existing plan content")
        mock_imp_repo = AsyncMock()
        mock_imp_repo.get_by_id = AsyncMock(return_value=improvement)
        mock_imp_repo_cls = MagicMock(return_value=mock_imp_repo)

        mock_cb = MagicMock()
        mock_cb.is_call_allowed.return_value = True

        mock_bot = _make_bot_mock()

        session = AsyncMock()
        sf = _make_session_factory(session)

        with (
            patch(
                "src.worker.tasks.interviews._load_circuit_breaker_config",
                new=AsyncMock(return_value=(True, 5, 60)),
            ),
            patch("src.worker.circuit_breaker.CircuitBreaker", return_value=mock_cb),
            patch("aiogram.Bot", return_value=mock_bot),
            patch("aiogram.client.default.DefaultBotProperties"),
            patch("src.config.settings", bot_token="fake_token"),
            patch("src.repositories.interview.InterviewImprovementRepository", mock_imp_repo_cls),
        ):
            result = await _generate_flow_async(sf, _make_fake_task(), 10, 1, 100, 200, "ru")

        assert result == {"status": "already_completed"}
        mock_bot.session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_success_calls_generate_and_edits_message(self):
        from src.worker.tasks.interviews import _generate_flow_async

        interview = _make_interview()
        improvement_before = _make_improvement(improvement_flow=None)
        improvement_after = _make_improvement(improvement_flow="Step 1: ...\nStep 2: ...")

        mock_imp_repo = AsyncMock()
        mock_imp_repo.get_by_id = AsyncMock(side_effect=[improvement_before, improvement_after])
        mock_imp_repo_cls = MagicMock(return_value=mock_imp_repo)

        mock_interview_repo = AsyncMock()
        mock_interview_repo.get_by_id = AsyncMock(return_value=interview)
        mock_interview_repo_cls = MagicMock(return_value=mock_interview_repo)

        mock_cb = MagicMock()
        mock_cb.is_call_allowed.return_value = True

        mock_bot = _make_bot_mock()

        mock_generate = AsyncMock(return_value="Step 1: ...\nStep 2: ...")
        mock_keyboard = MagicMock()
        mock_keyboard_fn = MagicMock(return_value=mock_keyboard)

        session = AsyncMock()
        sf = _make_session_factory(session)

        with (
            patch(
                "src.worker.tasks.interviews._load_circuit_breaker_config",
                new=AsyncMock(return_value=(True, 5, 60)),
            ),
            patch("src.worker.circuit_breaker.CircuitBreaker", return_value=mock_cb),
            patch("aiogram.Bot", return_value=mock_bot),
            patch("aiogram.client.default.DefaultBotProperties"),
            patch("src.config.settings", bot_token="fake_token"),
            patch("src.repositories.interview.InterviewImprovementRepository", mock_imp_repo_cls),
            patch("src.repositories.interview.InterviewRepository", mock_interview_repo_cls),
            patch(
                "src.bot.modules.interviews.services.generate_and_save_improvement_flow",
                mock_generate,
            ),
            patch(
                "src.bot.modules.interviews.keyboards.improvement_detail_keyboard",
                mock_keyboard_fn,
            ),
            patch(
                "src.bot.modules.interviews.services.format_vacancy_header",
                return_value="<b>Senior Python Developer</b>",
            ),
            patch("src.core.i18n.get_text", side_effect=lambda key, locale, **kw: key),
        ):
            result = await _generate_flow_async(sf, _make_fake_task(), 10, 1, 100, 200, "ru")

        assert result == {"status": "completed", "improvement_id": 10}
        mock_bot.edit_message_text.assert_called_once()
        mock_cb.record_success.assert_called_once()
        mock_bot.session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_notifies_user_and_retries_on_final_attempt(self):
        from src.worker.tasks.interviews import _generate_flow_async

        improvement = _make_improvement(improvement_flow=None)
        mock_imp_repo = AsyncMock()
        mock_imp_repo.get_by_id = AsyncMock(return_value=improvement)
        mock_imp_repo_cls = MagicMock(return_value=mock_imp_repo)

        mock_interview_repo = AsyncMock()
        mock_interview_repo.get_by_id = AsyncMock(return_value=_make_interview())
        mock_interview_repo_cls = MagicMock(return_value=mock_interview_repo)

        mock_cb = MagicMock()
        mock_cb.is_call_allowed.return_value = True

        mock_bot = _make_bot_mock()

        task = _make_fake_task(retries=2, max_retries=2)
        task.retry.side_effect = RuntimeError("max retries exceeded")

        session = AsyncMock()
        sf = _make_session_factory(session)

        with (
            patch(
                "src.worker.tasks.interviews._load_circuit_breaker_config",
                new=AsyncMock(return_value=(True, 5, 60)),
            ),
            patch("src.worker.circuit_breaker.CircuitBreaker", return_value=mock_cb),
            patch("aiogram.Bot", return_value=mock_bot),
            patch("aiogram.client.default.DefaultBotProperties"),
            patch("src.config.settings", bot_token="fake_token"),
            patch("src.repositories.interview.InterviewImprovementRepository", mock_imp_repo_cls),
            patch("src.repositories.interview.InterviewRepository", mock_interview_repo_cls),
            patch(
                "src.bot.modules.interviews.services.generate_and_save_improvement_flow",
                new=AsyncMock(side_effect=ValueError("AI service down")),
            ),
            patch("src.core.i18n.get_text", side_effect=lambda key, locale, **kw: key),
            pytest.raises(RuntimeError, match="max retries exceeded"),
        ):
            await _generate_flow_async(sf, task, 10, 1, 100, 200, "ru")

        task.retry.assert_called_once()
        mock_bot.edit_message_text.assert_called_once()
        call_kwargs = mock_bot.edit_message_text.call_args.kwargs
        assert call_kwargs["text"] == "iv-flow-generation-failed"

    @pytest.mark.asyncio
    async def test_retries_without_notifying_on_non_final_attempt(self):
        from src.worker.tasks.interviews import _generate_flow_async

        improvement = _make_improvement(improvement_flow=None)
        mock_imp_repo = AsyncMock()
        mock_imp_repo.get_by_id = AsyncMock(return_value=improvement)
        mock_imp_repo_cls = MagicMock(return_value=mock_imp_repo)

        mock_interview_repo = AsyncMock()
        mock_interview_repo.get_by_id = AsyncMock(return_value=_make_interview())
        mock_interview_repo_cls = MagicMock(return_value=mock_interview_repo)

        mock_cb = MagicMock()
        mock_cb.is_call_allowed.return_value = True

        mock_bot = _make_bot_mock()

        task = _make_fake_task(retries=0, max_retries=2)
        task.retry.side_effect = RuntimeError("retry scheduled")

        session = AsyncMock()
        sf = _make_session_factory(session)

        with (
            patch(
                "src.worker.tasks.interviews._load_circuit_breaker_config",
                new=AsyncMock(return_value=(True, 5, 60)),
            ),
            patch("src.worker.circuit_breaker.CircuitBreaker", return_value=mock_cb),
            patch("aiogram.Bot", return_value=mock_bot),
            patch("aiogram.client.default.DefaultBotProperties"),
            patch("src.config.settings", bot_token="fake_token"),
            patch("src.repositories.interview.InterviewImprovementRepository", mock_imp_repo_cls),
            patch("src.repositories.interview.InterviewRepository", mock_interview_repo_cls),
            patch(
                "src.bot.modules.interviews.services.generate_and_save_improvement_flow",
                new=AsyncMock(side_effect=ValueError("transient error")),
            ),
            patch("src.core.i18n.get_text", side_effect=lambda key, locale, **kw: key),
            pytest.raises(RuntimeError, match="retry scheduled"),
        ):
            await _generate_flow_async(sf, task, 10, 1, 100, 200, "ru")

        task.retry.assert_called_once()
        mock_bot.edit_message_text.assert_not_called()
