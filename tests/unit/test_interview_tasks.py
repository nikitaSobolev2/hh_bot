"""Unit tests for interview Celery tasks.

Covers: success path, circuit-breaker open path, idempotency skip path,
and disabled-setting path for both analyze and generate_flow tasks.

All async methods on the task object (HHBotTask subclass) are mocked via
AsyncMock attributes so tests never touch real Redis, DB, or the OpenAI API.
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
    task.check_enabled = AsyncMock(return_value=True)
    task.load_circuit_breaker = AsyncMock()
    task.is_already_completed = AsyncMock(return_value=False)
    task.mark_completed = AsyncMock()
    task.notify_user = AsyncMock()
    task.create_bot = MagicMock(return_value=_make_bot_mock())
    task.handle_soft_timeout = AsyncMock()
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


def _make_cb_mock(is_allowed: bool = True) -> MagicMock:
    cb = MagicMock()
    cb.is_call_allowed.return_value = is_allowed
    return cb


# ── analyze_interview_task ────────────────────────────────────────────────────


class TestAnalyzeInterviewTask:
    @pytest.mark.asyncio
    async def test_disabled_setting_returns_disabled(self):
        from src.worker.tasks.interviews import _analyze_interview_async

        task = _make_fake_task()
        task.check_enabled = AsyncMock(return_value=False)
        sf = _make_session_factory(AsyncMock())

        result = await _analyze_interview_async(task, sf, 1, 100, 200, "ru", None)

        assert result == {"status": "disabled"}

    @pytest.mark.asyncio
    async def test_circuit_open_returns_circuit_open(self):
        from src.worker.tasks.interviews import _analyze_interview_async

        task = _make_fake_task()
        task.load_circuit_breaker = AsyncMock(return_value=_make_cb_mock(is_allowed=False))
        sf = _make_session_factory(AsyncMock())

        result = await _analyze_interview_async(task, sf, 1, 100, 200, "ru", None)

        assert result == {"status": "circuit_open"}

    @pytest.mark.asyncio
    async def test_idempotency_skips_when_already_analyzed(self):
        from src.worker.tasks.interviews import _analyze_interview_async

        task = _make_fake_task()
        task.load_circuit_breaker = AsyncMock(return_value=_make_cb_mock())
        task.is_already_completed = AsyncMock(return_value=True)
        sf = _make_session_factory(AsyncMock())

        result = await _analyze_interview_async(task, sf, 1, 100, 200, "ru", None)

        assert result == {"status": "already_completed"}

    @pytest.mark.asyncio
    async def test_success_calls_analyze_and_notifies_user(self):
        from src.worker.tasks.interviews import _analyze_interview_async

        interview = _make_interview(ai_summary=None)
        mock_improvement = _make_improvement()
        mock_interview_repo = AsyncMock()
        mock_interview_repo.get_with_relations = AsyncMock(return_value=interview)

        task = _make_fake_task()
        task.load_circuit_breaker = AsyncMock(return_value=_make_cb_mock())
        session = AsyncMock()
        sf = _make_session_factory(session)

        mock_analyze = AsyncMock(return_value=("AI summary text", [mock_improvement]))
        mock_keyboard = MagicMock()

        with (
            patch(
                "src.repositories.interview.InterviewRepository",
                MagicMock(return_value=mock_interview_repo),
            ),
            patch("src.bot.modules.interviews.services.analyze_and_save", mock_analyze),
            patch(
                "src.bot.modules.interviews.keyboards.interview_detail_keyboard",
                return_value=mock_keyboard,
            ),
            patch(
                "src.bot.modules.interviews.services.format_vacancy_header",
                return_value="<b>Senior Python Developer</b>",
            ),
            patch("src.core.i18n.get_text", side_effect=lambda key, locale, **kw: key),
        ):
            result = await _analyze_interview_async(
                task, sf, 1, 100, 200, "ru", "I want to improve Python"
            )

        assert result == {"status": "completed", "interview_id": 1}
        task.notify_user.assert_called_once()
        task.mark_completed.assert_called_once()

    @pytest.mark.asyncio
    async def test_notifies_user_and_retries_on_final_attempt(self):
        from src.worker.tasks.interviews import _analyze_interview_async

        interview = _make_interview(ai_summary=None)
        mock_interview_repo = AsyncMock()
        mock_interview_repo.get_with_relations = AsyncMock(return_value=interview)

        task = _make_fake_task(retries=2, max_retries=2)
        task.load_circuit_breaker = AsyncMock(return_value=_make_cb_mock())
        task.retry = MagicMock(side_effect=RuntimeError("max retries exceeded"))
        session = AsyncMock()
        sf = _make_session_factory(session)

        with (
            patch(
                "src.repositories.interview.InterviewRepository",
                MagicMock(return_value=mock_interview_repo),
            ),
            patch(
                "src.bot.modules.interviews.services.analyze_and_save",
                new=AsyncMock(side_effect=ValueError("AI service down")),
            ),
            patch("src.core.i18n.get_text", side_effect=lambda key, locale, **kw: key),
            pytest.raises(RuntimeError, match="max retries exceeded"),
        ):
            await _analyze_interview_async(task, sf, 1, 100, 200, "ru", None)

        task.retry.assert_called_once()
        task.notify_user.assert_called_once()
        call_args = task.notify_user.call_args
        assert call_args[0][3] == "iv-analysis-failed"

    @pytest.mark.asyncio
    async def test_retries_without_notifying_on_non_final_attempt(self):
        from src.worker.tasks.interviews import _analyze_interview_async

        interview = _make_interview(ai_summary=None)
        mock_interview_repo = AsyncMock()
        mock_interview_repo.get_with_relations = AsyncMock(return_value=interview)

        task = _make_fake_task(retries=0, max_retries=2)
        task.load_circuit_breaker = AsyncMock(return_value=_make_cb_mock())
        task.retry = MagicMock(side_effect=RuntimeError("retry scheduled"))
        session = AsyncMock()
        sf = _make_session_factory(session)

        with (
            patch(
                "src.repositories.interview.InterviewRepository",
                MagicMock(return_value=mock_interview_repo),
            ),
            patch(
                "src.bot.modules.interviews.services.analyze_and_save",
                new=AsyncMock(side_effect=ValueError("transient error")),
            ),
            patch("src.core.i18n.get_text", side_effect=lambda key, locale, **kw: key),
            pytest.raises(RuntimeError, match="retry scheduled"),
        ):
            await _analyze_interview_async(task, sf, 1, 100, 200, "ru", None)

        task.retry.assert_called_once()
        task.notify_user.assert_not_called()


# ── generate_improvement_flow_task ────────────────────────────────────────────


class TestGenerateImprovementFlowTask:
    @pytest.mark.asyncio
    async def test_disabled_setting_returns_disabled(self):
        from src.worker.tasks.interviews import _generate_flow_async

        task = _make_fake_task()
        task.check_enabled = AsyncMock(return_value=False)
        sf = _make_session_factory(AsyncMock())

        result = await _generate_flow_async(task, sf, 10, 1, 100, 200, "ru")

        assert result == {"status": "disabled"}

    @pytest.mark.asyncio
    async def test_circuit_open_returns_circuit_open(self):
        from src.worker.tasks.interviews import _generate_flow_async

        task = _make_fake_task()
        task.load_circuit_breaker = AsyncMock(return_value=_make_cb_mock(is_allowed=False))
        sf = _make_session_factory(AsyncMock())

        result = await _generate_flow_async(task, sf, 10, 1, 100, 200, "ru")

        assert result == {"status": "circuit_open"}

    @pytest.mark.asyncio
    async def test_idempotency_skips_when_flow_already_generated(self):
        from src.worker.tasks.interviews import _generate_flow_async

        task = _make_fake_task()
        task.load_circuit_breaker = AsyncMock(return_value=_make_cb_mock())
        task.is_already_completed = AsyncMock(return_value=True)
        sf = _make_session_factory(AsyncMock())

        result = await _generate_flow_async(task, sf, 10, 1, 100, 200, "ru")

        assert result == {"status": "already_completed"}

    @pytest.mark.asyncio
    async def test_success_calls_generate_and_notifies_user(self):
        from src.worker.tasks.interviews import _generate_flow_async

        interview = _make_interview()
        improvement_before = _make_improvement(improvement_flow=None)
        improvement_after = _make_improvement(improvement_flow="Step 1: ...\nStep 2: ...")

        mock_imp_repo = AsyncMock()
        mock_imp_repo.get_by_id = AsyncMock(side_effect=[improvement_before, improvement_after])
        mock_interview_repo = AsyncMock()
        mock_interview_repo.get_by_id = AsyncMock(return_value=interview)

        task = _make_fake_task()
        task.load_circuit_breaker = AsyncMock(return_value=_make_cb_mock())
        session = AsyncMock()
        sf = _make_session_factory(session)

        with (
            patch(
                "src.repositories.interview.InterviewImprovementRepository",
                MagicMock(return_value=mock_imp_repo),
            ),
            patch(
                "src.repositories.interview.InterviewRepository",
                MagicMock(return_value=mock_interview_repo),
            ),
            patch(
                "src.bot.modules.interviews.services.generate_and_save_improvement_flow",
                AsyncMock(return_value="Step 1: ...\nStep 2: ..."),
            ),
            patch(
                "src.bot.modules.interviews.keyboards.improvement_detail_keyboard",
                return_value=MagicMock(),
            ),
            patch(
                "src.bot.modules.interviews.services.format_vacancy_header",
                return_value="<b>Senior Python Developer</b>",
            ),
            patch("src.core.i18n.get_text", side_effect=lambda key, locale, **kw: key),
        ):
            result = await _generate_flow_async(task, sf, 10, 1, 100, 200, "ru")

        assert result == {"status": "completed", "improvement_id": 10}
        task.notify_user.assert_called_once()
        task.mark_completed.assert_called_once()

    @pytest.mark.asyncio
    async def test_notifies_user_and_retries_on_final_attempt(self):
        from src.worker.tasks.interviews import _generate_flow_async

        improvement = _make_improvement(improvement_flow=None)
        mock_imp_repo = AsyncMock()
        mock_imp_repo.get_by_id = AsyncMock(return_value=improvement)
        mock_interview_repo = AsyncMock()
        mock_interview_repo.get_by_id = AsyncMock(return_value=_make_interview())

        task = _make_fake_task(retries=2, max_retries=2)
        task.load_circuit_breaker = AsyncMock(return_value=_make_cb_mock())
        task.retry = MagicMock(side_effect=RuntimeError("max retries exceeded"))
        session = AsyncMock()
        sf = _make_session_factory(session)

        with (
            patch(
                "src.repositories.interview.InterviewImprovementRepository",
                MagicMock(return_value=mock_imp_repo),
            ),
            patch(
                "src.repositories.interview.InterviewRepository",
                MagicMock(return_value=mock_interview_repo),
            ),
            patch(
                "src.bot.modules.interviews.services.generate_and_save_improvement_flow",
                new=AsyncMock(side_effect=ValueError("AI service down")),
            ),
            patch("src.core.i18n.get_text", side_effect=lambda key, locale, **kw: key),
            pytest.raises(RuntimeError, match="max retries exceeded"),
        ):
            await _generate_flow_async(task, sf, 10, 1, 100, 200, "ru")

        task.retry.assert_called_once()
        task.notify_user.assert_called_once()
        call_args = task.notify_user.call_args
        assert call_args[0][3] == "iv-flow-generation-failed"

    @pytest.mark.asyncio
    async def test_retries_without_notifying_on_non_final_attempt(self):
        from src.worker.tasks.interviews import _generate_flow_async

        improvement = _make_improvement(improvement_flow=None)
        mock_imp_repo = AsyncMock()
        mock_imp_repo.get_by_id = AsyncMock(return_value=improvement)
        mock_interview_repo = AsyncMock()
        mock_interview_repo.get_by_id = AsyncMock(return_value=_make_interview())

        task = _make_fake_task(retries=0, max_retries=2)
        task.load_circuit_breaker = AsyncMock(return_value=_make_cb_mock())
        task.retry = MagicMock(side_effect=RuntimeError("retry scheduled"))
        session = AsyncMock()
        sf = _make_session_factory(session)

        with (
            patch(
                "src.repositories.interview.InterviewImprovementRepository",
                MagicMock(return_value=mock_imp_repo),
            ),
            patch(
                "src.repositories.interview.InterviewRepository",
                MagicMock(return_value=mock_interview_repo),
            ),
            patch(
                "src.bot.modules.interviews.services.generate_and_save_improvement_flow",
                new=AsyncMock(side_effect=ValueError("transient error")),
            ),
            patch("src.core.i18n.get_text", side_effect=lambda key, locale, **kw: key),
            pytest.raises(RuntimeError, match="retry scheduled"),
        ):
            await _generate_flow_async(task, sf, 10, 1, 100, 200, "ru")

        task.retry.assert_called_once()
        task.notify_user.assert_not_called()


# ── generate_company_review_task ───────────────────────────────────────────────


class TestGenerateCompanyReviewTask:
    @pytest.mark.asyncio
    async def test_disabled_setting_returns_disabled(self):
        from src.worker.tasks.interviews import _generate_company_review_async

        task = _make_fake_task()
        task.check_enabled = AsyncMock(return_value=False)
        sf = _make_session_factory(AsyncMock())

        result = await _generate_company_review_async(
            task, sf, 1, 100, 200, "ru"
        )

        assert result == {"status": "disabled"}

    @pytest.mark.asyncio
    async def test_success_notifies_user(self):
        from src.worker.tasks.interviews import _generate_company_review_async

        interview = _make_interview()
        mock_interview_repo = AsyncMock()
        mock_interview_repo.get_with_relations = AsyncMock(return_value=interview)

        task = _make_fake_task()
        task.load_circuit_breaker = AsyncMock(return_value=_make_cb_mock())
        session = AsyncMock()
        sf = _make_session_factory(session)

        with (
            patch(
                "src.repositories.interview.InterviewRepository",
                MagicMock(return_value=mock_interview_repo),
            ),
            patch(
                "src.services.ai.client.AIClient",
                MagicMock(
                    return_value=MagicMock(
                        generate_text=AsyncMock(
                            return_value="Company review text"
                        )
                    ),
                ),
            ),
            patch(
                "src.bot.modules.interviews.keyboards.interview_detail_keyboard",
                return_value=MagicMock(),
            ),
            patch("src.core.i18n.get_text", side_effect=lambda key, locale, **kw: key),
        ):
            result = await _generate_company_review_async(
                task, sf, 1, 100, 200, "ru"
            )

        assert result == {"status": "completed", "interview_id": 1}
        task.notify_user.assert_called_once()


# ── generate_questions_to_ask_task ─────────────────────────────────────────────


class TestGenerateQuestionsToAskTask:
    @pytest.mark.asyncio
    async def test_disabled_setting_returns_disabled(self):
        from src.worker.tasks.interviews import _generate_questions_to_ask_async

        task = _make_fake_task()
        task.check_enabled = AsyncMock(return_value=False)
        sf = _make_session_factory(AsyncMock())

        result = await _generate_questions_to_ask_async(
            task, sf, 1, 100, 200, "ru"
        )

        assert result == {"status": "disabled"}

    @pytest.mark.asyncio
    async def test_success_notifies_user(self):
        from src.worker.tasks.interviews import _generate_questions_to_ask_async

        interview = _make_interview()
        mock_interview_repo = AsyncMock()
        mock_interview_repo.get_with_relations = AsyncMock(return_value=interview)

        task = _make_fake_task()
        task.load_circuit_breaker = AsyncMock(return_value=_make_cb_mock())
        session = AsyncMock()
        sf = _make_session_factory(session)

        with (
            patch(
                "src.repositories.interview.InterviewRepository",
                MagicMock(return_value=mock_interview_repo),
            ),
            patch(
                "src.services.ai.client.AIClient",
                MagicMock(
                    return_value=MagicMock(
                        generate_text=AsyncMock(
                            return_value="**HR:** Q1\n**Tech Lead:** Q2"
                        )
                    ),
                ),
            ),
            patch(
                "src.bot.modules.interviews.keyboards.interview_detail_keyboard",
                return_value=MagicMock(),
            ),
            patch("src.core.i18n.get_text", side_effect=lambda key, locale, **kw: key),
        ):
            result = await _generate_questions_to_ask_async(
                task, sf, 1, 100, 200, "ru"
            )

        assert result == {"status": "completed", "interview_id": 1}
        task.notify_user.assert_called_once()


# ── generate_test_task (interview_prep) ────────────────────────────────────────


def _make_prep_step(title: str = "Python basics", content: str = "Content") -> MagicMock:
    step = MagicMock()
    step.id = 1
    step.title = title
    step.content = content
    step.deep_summary = "Summary"
    return step


class TestGenerateTestTask:
    @pytest.mark.asyncio
    async def test_disabled_setting_returns_disabled(self):
        from src.worker.tasks.interview_prep import _generate_test_async

        task = _make_fake_task()
        task.check_enabled = AsyncMock(return_value=False)
        sf = _make_session_factory(AsyncMock())

        result = await _generate_test_async(task, sf, 1, 1, 100, 200, "ru")

        assert result == {"status": "disabled"}

    @pytest.mark.asyncio
    async def test_circuit_open_returns_circuit_open(self):
        from src.worker.tasks.interview_prep import _generate_test_async

        task = _make_fake_task()
        task.load_circuit_breaker = AsyncMock(return_value=_make_cb_mock(is_allowed=False))
        sf = _make_session_factory(AsyncMock())

        result = await _generate_test_async(task, sf, 1, 1, 100, 200, "ru")

        assert result == {"status": "circuit_open"}

    @pytest.mark.asyncio
    async def test_success_creates_new_test_when_none_exists(self):
        from src.worker.tasks.interview_prep import _generate_test_async

        step = _make_prep_step()
        mock_prep_repo = AsyncMock()
        mock_prep_repo.get_step_by_id = AsyncMock(return_value=step)
        mock_prep_repo.get_test_by_step = AsyncMock(return_value=None)

        task = _make_fake_task()
        task.load_circuit_breaker = AsyncMock(return_value=_make_cb_mock())
        session = AsyncMock()
        session.add = MagicMock()
        sf = _make_session_factory(session)

        with (
            patch(
                "src.repositories.interview.InterviewPreparationRepository",
                MagicMock(return_value=mock_prep_repo),
            ),
            patch(
                "src.services.ai.client.AIClient",
                MagicMock(
                    return_value=MagicMock(
                        generate_text=AsyncMock(
                            return_value="[Q]:What is Python?\n[A]:A language*\n[TestEnd]"
                        )
                    ),
                ),
            ),
            patch("src.core.i18n.get_text", side_effect=lambda key, locale, **kw: key),
        ):
            result = await _generate_test_async(task, sf, 1, 1, 100, 200, "ru")

        assert result == {"status": "completed", "questions_count": 1}
        mock_prep_repo.get_test_by_step.assert_called_once_with(1)
        session.add.assert_called_once()
        session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_success_updates_existing_test_when_one_exists(self):
        from src.worker.tasks.interview_prep import _generate_test_async

        step = _make_prep_step()
        existing_test = MagicMock()
        existing_test.questions_json = {"questions": []}
        existing_test.user_answers_json = {"answers": []}

        mock_prep_repo = AsyncMock()
        mock_prep_repo.get_step_by_id = AsyncMock(return_value=step)
        mock_prep_repo.get_test_by_step = AsyncMock(return_value=existing_test)

        task = _make_fake_task()
        task.load_circuit_breaker = AsyncMock(return_value=_make_cb_mock())
        session = AsyncMock()
        sf = _make_session_factory(session)

        with (
            patch(
                "src.repositories.interview.InterviewPreparationRepository",
                MagicMock(return_value=mock_prep_repo),
            ),
            patch(
                "src.services.ai.client.AIClient",
                MagicMock(
                    return_value=MagicMock(
                        generate_text=AsyncMock(
                            return_value="[Q]:What is Python?\n[A]:A language*\n[TestEnd]"
                        )
                    ),
                ),
            ),
            patch("src.core.i18n.get_text", side_effect=lambda key, locale, **kw: key),
        ):
            result = await _generate_test_async(task, sf, 1, 1, 100, 200, "ru")

        assert result == {"status": "completed", "questions_count": 1}
        mock_prep_repo.get_test_by_step.assert_called_once_with(1)
        assert existing_test.questions_json == {
            "questions": [
                {"question": "What is Python?", "options": ["A language"], "correct_index": 0}
            ]
        }
        assert existing_test.user_answers_json is None
        session.add.assert_not_called()
