"""Unit tests for the Interview Q&A module.

Covers: handlers (generate_all, generate_one, generate_pending, regenerate),
keyboard builder (generate_select_keyboard), and Celery task (_generate_qa_async).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.i18n import I18nContext

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_i18n() -> I18nContext:
    return I18nContext(locale="en")


def _make_callback(chat_id: int = 42, message_id: int = 10) -> MagicMock:
    callback = AsyncMock()
    callback.message = AsyncMock()
    callback.message.chat = MagicMock()
    callback.message.chat.id = chat_id
    callback.message.message_id = message_id
    wait_msg = AsyncMock()
    wait_msg.message_id = 99
    callback.message.edit_text = AsyncMock(return_value=wait_msg)
    return callback


def _make_user(user_id: int = 1, language_code: str = "en") -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.language_code = language_code
    return user


def _make_session() -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    return session


def _make_question(key: str = "best_achievement", answer: str | None = "Great answer") -> MagicMock:
    q = MagicMock()
    q.question_key = key
    q.question_text = f"Question about {key}"
    q.answer_text = answer
    return q


def _make_session_factory(session: AsyncMock):
    @asynccontextmanager
    async def _factory():
        yield session

    return _factory


# ── generate_select_keyboard ──────────────────────────────────────────────────


class TestGenerateSelectKeyboard:
    def test_marks_generated_keys_with_checkmark(self):
        from src.bot.modules.interview_qa.keyboards import generate_select_keyboard

        generated = {"best_achievement", "five_year_plan"}
        kb = generate_select_keyboard(generated, _make_i18n())

        button_texts = [btn.text for row in kb.inline_keyboard for btn in row]
        checkmark_buttons = [t for t in button_texts if t.startswith("✅")]
        cross_buttons = [t for t in button_texts if t.startswith("❌")]

        assert len(checkmark_buttons) == 2
        assert len(cross_buttons) == 4

    def test_all_generated_hides_pending_button(self):
        from src.bot.modules.interview_qa.keyboards import generate_select_keyboard
        from src.models.interview_qa import BASE_QUESTION_KEYS

        all_keys = {k for k in BASE_QUESTION_KEYS if k != "why_new_job"}
        kb = generate_select_keyboard(all_keys, _make_i18n())

        button_texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert not any("remaining" in t for t in button_texts)

    def test_pending_button_shows_count_when_some_not_generated(self):
        from src.bot.modules.interview_qa.keyboards import generate_select_keyboard

        kb = generate_select_keyboard(set(), _make_i18n())

        button_texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("6" in t for t in button_texts)

    def test_why_new_job_key_is_excluded_from_list(self):
        from src.bot.modules.interview_qa.keyboards import generate_select_keyboard

        kb = generate_select_keyboard(set(), _make_i18n())

        all_callback_data = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert not any("why_new_job" in (cd or "") for cd in all_callback_data)

    def test_back_button_is_always_last(self):
        from src.bot.modules.interview_qa.keyboards import generate_select_keyboard

        kb = generate_select_keyboard(set(), _make_i18n())

        last_row = kb.inline_keyboard[-1]
        assert len(last_row) == 1
        assert "iqa:list" in last_row[0].callback_data


# ── handle_generate_all ───────────────────────────────────────────────────────


class TestHandleGenerateAll:
    @pytest.mark.asyncio
    async def test_shows_alert_when_no_work_experience(self):
        from src.bot.modules.interview_qa.handlers import handle_generate_all

        callback = _make_callback()
        user = _make_user()
        session = _make_session()
        i18n = _make_i18n()

        mock_we_repo = AsyncMock()
        mock_we_repo.count_active_by_user = AsyncMock(return_value=0)

        with patch(
            "src.bot.modules.interview_qa.handlers.WorkExperienceRepository",
            return_value=mock_we_repo,
        ):
            await handle_generate_all(callback, user, session, i18n)

        callback.answer.assert_called_once()
        call_kwargs = callback.answer.call_args.kwargs
        assert call_kwargs.get("show_alert") is True
        callback.message.edit_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_shows_selection_screen_when_work_experience_exists(self):
        from src.bot.modules.interview_qa.handlers import handle_generate_all

        callback = _make_callback()
        user = _make_user()
        session = _make_session()
        i18n = _make_i18n()

        mock_we_repo = AsyncMock()
        mock_we_repo.count_active_by_user = AsyncMock(return_value=2)

        mock_qa_repo = AsyncMock()
        mock_qa_repo.get_ai_generated = AsyncMock(return_value=[])

        with (
            patch(
                "src.bot.modules.interview_qa.handlers.WorkExperienceRepository",
                return_value=mock_we_repo,
            ),
            patch(
                "src.bot.modules.interview_qa.handlers.StandardQuestionRepository",
                return_value=mock_qa_repo,
            ),
        ):
            await handle_generate_all(callback, user, session, i18n)

        callback.message.edit_text.assert_called_once()
        edit_kwargs = callback.message.edit_text.call_args.kwargs
        assert edit_kwargs.get("reply_markup") is not None

    @pytest.mark.asyncio
    async def test_does_not_dispatch_celery_task(self):
        from src.bot.modules.interview_qa.handlers import handle_generate_all

        callback = _make_callback()
        user = _make_user()
        session = _make_session()
        i18n = _make_i18n()

        mock_we_repo = AsyncMock()
        mock_we_repo.count_active_by_user = AsyncMock(return_value=1)

        mock_qa_repo = AsyncMock()
        mock_qa_repo.get_ai_generated = AsyncMock(return_value=[])

        mock_task = MagicMock()

        with (
            patch(
                "src.bot.modules.interview_qa.handlers.WorkExperienceRepository",
                return_value=mock_we_repo,
            ),
            patch(
                "src.bot.modules.interview_qa.handlers.StandardQuestionRepository",
                return_value=mock_qa_repo,
            ),
            patch(
                "src.worker.tasks.interview_qa.generate_interview_qa_task",
                mock_task,
            ),
        ):
            await handle_generate_all(callback, user, session, i18n)

        mock_task.delay.assert_not_called()


# ── handle_generate_one ───────────────────────────────────────────────────────


class TestHandleGenerateOne:
    @pytest.mark.asyncio
    async def test_shows_alert_when_no_work_experience(self):
        from src.bot.modules.interview_qa.callbacks import InterviewQACallback
        from src.bot.modules.interview_qa.handlers import handle_generate_one

        callback = _make_callback()
        callback_data = InterviewQACallback(action="generate_one", question_key="best_achievement")
        user = _make_user()
        session = _make_session()
        i18n = _make_i18n()

        mock_we_repo = AsyncMock()
        mock_we_repo.count_active_by_user = AsyncMock(return_value=0)

        with patch(
            "src.bot.modules.interview_qa.handlers.WorkExperienceRepository",
            return_value=mock_we_repo,
        ):
            await handle_generate_one(callback, callback_data, user, session, i18n)

        callback.answer.assert_called_once()
        assert callback.answer.call_args.kwargs.get("show_alert") is True

    @pytest.mark.asyncio
    async def test_soft_deletes_existing_answer_before_dispatch(self):
        from src.bot.modules.interview_qa.callbacks import InterviewQACallback
        from src.bot.modules.interview_qa.handlers import handle_generate_one

        existing_question = _make_question("best_achievement")
        callback = _make_callback()
        callback_data = InterviewQACallback(action="generate_one", question_key="best_achievement")
        user = _make_user()
        session = _make_session()
        i18n = _make_i18n()

        mock_we_repo = AsyncMock()
        mock_we_repo.count_active_by_user = AsyncMock(return_value=1)

        mock_qa_repo = AsyncMock()
        mock_qa_repo.get_by_key = AsyncMock(return_value=existing_question)
        mock_qa_repo.soft_delete = AsyncMock()

        mock_task = MagicMock()

        with (
            patch(
                "src.bot.modules.interview_qa.handlers.WorkExperienceRepository",
                return_value=mock_we_repo,
            ),
            patch(
                "src.bot.modules.interview_qa.handlers.StandardQuestionRepository",
                return_value=mock_qa_repo,
            ),
            patch(
                "src.worker.tasks.interview_qa.generate_interview_qa_task",
                mock_task,
            ),
        ):
            await handle_generate_one(callback, callback_data, user, session, i18n)

        mock_qa_repo.soft_delete.assert_called_once_with(existing_question)
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatches_task_with_specific_question_key(self):
        from src.bot.modules.interview_qa.callbacks import InterviewQACallback
        from src.bot.modules.interview_qa.handlers import handle_generate_one

        callback = _make_callback(chat_id=42, message_id=10)
        callback_data = InterviewQACallback(action="generate_one", question_key="five_year_plan")
        user = _make_user(user_id=7, language_code="ru")
        session = _make_session()
        i18n = _make_i18n()

        mock_we_repo = AsyncMock()
        mock_we_repo.count_active_by_user = AsyncMock(return_value=1)

        mock_qa_repo = AsyncMock()
        mock_qa_repo.get_by_key = AsyncMock(return_value=None)

        mock_task = MagicMock()

        with (
            patch(
                "src.bot.modules.interview_qa.handlers.WorkExperienceRepository",
                return_value=mock_we_repo,
            ),
            patch(
                "src.bot.modules.interview_qa.handlers.StandardQuestionRepository",
                return_value=mock_qa_repo,
            ),
            patch(
                "src.worker.tasks.interview_qa.generate_interview_qa_task",
                mock_task,
            ),
        ):
            await handle_generate_one(callback, callback_data, user, session, i18n)

        mock_task.delay.assert_called_once()
        delay_args = mock_task.delay.call_args.args
        assert delay_args[0] == 7
        assert delay_args[4] == "five_year_plan"

    @pytest.mark.asyncio
    async def test_skips_soft_delete_when_no_existing_answer(self):
        from src.bot.modules.interview_qa.callbacks import InterviewQACallback
        from src.bot.modules.interview_qa.handlers import handle_generate_one

        callback = _make_callback()
        callback_data = InterviewQACallback(action="generate_one", question_key="team_conflict")
        user = _make_user()
        session = _make_session()
        i18n = _make_i18n()

        mock_we_repo = AsyncMock()
        mock_we_repo.count_active_by_user = AsyncMock(return_value=1)

        mock_qa_repo = AsyncMock()
        mock_qa_repo.get_by_key = AsyncMock(return_value=None)
        mock_qa_repo.soft_delete = AsyncMock()

        mock_task = MagicMock()

        with (
            patch(
                "src.bot.modules.interview_qa.handlers.WorkExperienceRepository",
                return_value=mock_we_repo,
            ),
            patch(
                "src.bot.modules.interview_qa.handlers.StandardQuestionRepository",
                return_value=mock_qa_repo,
            ),
            patch(
                "src.worker.tasks.interview_qa.generate_interview_qa_task",
                mock_task,
            ),
        ):
            await handle_generate_one(callback, callback_data, user, session, i18n)

        mock_qa_repo.soft_delete.assert_not_called()
        session.commit.assert_not_called()


# ── handle_generate_pending ───────────────────────────────────────────────────


class TestHandleGeneratePending:
    @pytest.mark.asyncio
    async def test_shows_alert_when_no_work_experience(self):
        from src.bot.modules.interview_qa.handlers import handle_generate_pending

        callback = _make_callback()
        user = _make_user()
        session = _make_session()
        i18n = _make_i18n()

        mock_we_repo = AsyncMock()
        mock_we_repo.count_active_by_user = AsyncMock(return_value=0)

        with patch(
            "src.bot.modules.interview_qa.handlers.WorkExperienceRepository",
            return_value=mock_we_repo,
        ):
            await handle_generate_pending(callback, user, session, i18n)

        callback.answer.assert_called_once()
        assert callback.answer.call_args.kwargs.get("show_alert") is True
        callback.message.edit_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatches_task_without_question_key(self):
        from src.bot.modules.interview_qa.handlers import handle_generate_pending

        callback = _make_callback(chat_id=55, message_id=20)
        user = _make_user(user_id=3, language_code="ru")
        session = _make_session()
        i18n = _make_i18n()

        mock_we_repo = AsyncMock()
        mock_we_repo.count_active_by_user = AsyncMock(return_value=1)

        mock_task = MagicMock()

        with (
            patch(
                "src.bot.modules.interview_qa.handlers.WorkExperienceRepository",
                return_value=mock_we_repo,
            ),
            patch(
                "src.worker.tasks.interview_qa.generate_interview_qa_task",
                mock_task,
            ),
        ):
            await handle_generate_pending(callback, user, session, i18n)

        mock_task.delay.assert_called_once()
        delay_args = mock_task.delay.call_args.args
        assert delay_args[0] == 3
        assert len(delay_args) == 4


# ── handle_regenerate ─────────────────────────────────────────────────────────


class TestHandleRegenerate:
    @pytest.mark.asyncio
    async def test_passes_specific_question_key_to_task(self):
        from src.bot.modules.interview_qa.callbacks import InterviewQACallback
        from src.bot.modules.interview_qa.handlers import handle_regenerate

        existing_question = _make_question("worst_achievement")
        callback = _make_callback(chat_id=10, message_id=5)
        callback_data = InterviewQACallback(action="regenerate", question_key="worst_achievement")
        user = _make_user(user_id=9, language_code="en")
        session = _make_session()
        i18n = _make_i18n()

        mock_repo = AsyncMock()
        mock_repo.get_by_key = AsyncMock(return_value=existing_question)
        mock_repo.soft_delete = AsyncMock()

        mock_task_repo = AsyncMock()
        mock_task_repo.delete_by_idempotency_key = AsyncMock(return_value=True)

        mock_task = MagicMock()

        with (
            patch(
                "src.bot.modules.interview_qa.handlers.StandardQuestionRepository",
                return_value=mock_repo,
            ),
            patch(
                "src.repositories.task.CeleryTaskRepository",
                return_value=mock_task_repo,
            ),
            patch(
                "src.worker.tasks.interview_qa.generate_interview_qa_task",
                mock_task,
            ),
        ):
            await handle_regenerate(callback, callback_data, user, session, i18n)

        mock_task_repo.delete_by_idempotency_key.assert_called_once()
        mock_task.delay.assert_called_once()
        delay_args = mock_task.delay.call_args.args
        assert delay_args[4] == "worst_achievement"

    @pytest.mark.asyncio
    async def test_soft_deletes_before_dispatching(self):
        from src.bot.modules.interview_qa.callbacks import InterviewQACallback
        from src.bot.modules.interview_qa.handlers import handle_regenerate

        existing_question = _make_question("biggest_challenge")
        callback = _make_callback()
        callback_data = InterviewQACallback(action="regenerate", question_key="biggest_challenge")
        user = _make_user()
        session = _make_session()
        i18n = _make_i18n()

        mock_repo = AsyncMock()
        mock_repo.get_by_key = AsyncMock(return_value=existing_question)
        mock_repo.soft_delete = AsyncMock()

        mock_task_repo = AsyncMock()
        mock_task_repo.delete_by_idempotency_key = AsyncMock(return_value=True)

        mock_task = MagicMock()

        with (
            patch(
                "src.bot.modules.interview_qa.handlers.StandardQuestionRepository",
                return_value=mock_repo,
            ),
            patch(
                "src.repositories.task.CeleryTaskRepository",
                return_value=mock_task_repo,
            ),
            patch(
                "src.worker.tasks.interview_qa.generate_interview_qa_task",
                mock_task,
            ),
        ):
            await handle_regenerate(callback, callback_data, user, session, i18n)

        mock_repo.soft_delete.assert_called_once_with(existing_question)
        mock_task_repo.delete_by_idempotency_key.assert_called_once()
        session.commit.assert_called()


# ── _generate_qa_async ────────────────────────────────────────────────────────


def _make_mock_task(mock_cb=None, mock_bot=None):
    """Return a mock HHBotTask with stubbed shared helpers."""
    task = MagicMock()
    task.check_enabled = AsyncMock(return_value=True)
    task.is_already_completed = AsyncMock(return_value=False)
    task.mark_completed = AsyncMock()
    task.load_circuit_breaker = AsyncMock(return_value=mock_cb or MagicMock())
    task.create_bot = MagicMock(return_value=mock_bot or AsyncMock())
    task.notify_user = AsyncMock()
    return task


class TestGenerateQaAsync:
    @pytest.mark.asyncio
    async def test_with_specific_question_key_generates_only_that_key(self):
        from src.worker.tasks.interview_qa import _generate_qa_async

        session = AsyncMock()
        session.commit = AsyncMock()
        sf = _make_session_factory(session)

        mock_cb = MagicMock()
        mock_cb.is_call_allowed.return_value = True

        fake_experience = MagicMock(company_name="Acme", stack="Python")
        mock_we_repo = AsyncMock()
        mock_we_repo.get_active_by_user = AsyncMock(return_value=[fake_experience])

        mock_qa_repo = AsyncMock()
        mock_qa_repo.get_ai_generated = AsyncMock(return_value=[])
        mock_qa_repo.upsert_answer = AsyncMock()

        mock_bot = AsyncMock()
        mock_bot.session = AsyncMock()

        raw_response = (
            "[QAStart]:best_achievement\nI achieved great things.[QAEnd]:best_achievement"
        )

        mock_ai_client = MagicMock()
        mock_ai_client.generate_text = AsyncMock(return_value=raw_response)

        mock_task = _make_mock_task(mock_cb=mock_cb, mock_bot=mock_bot)

        _we_path = "src.repositories.work_experience.WorkExperienceRepository"
        _qa_path = "src.repositories.interview_qa.StandardQuestionRepository"
        with (
            patch(_we_path, return_value=mock_we_repo),
            patch(_qa_path, return_value=mock_qa_repo),
            patch("src.services.ai.client.AIClient", return_value=mock_ai_client),
            patch("src.config.settings", bot_token="fake"),
            patch("src.core.i18n.get_text", side_effect=lambda key, locale, **kw: key),
            patch(
                "src.services.ai.prompts.build_standard_qa_system_prompt",
                return_value="system prompt",
            ),
            patch(
                "src.services.ai.prompts.build_standard_qa_user_content",
                return_value="user content",
            ),
        ):
            result = await _generate_qa_async(mock_task, sf, 1, 100, 200, "en", "best_achievement")

        assert result["status"] == "completed"
        mock_qa_repo.upsert_answer.assert_called_once()
        upsert_call = mock_qa_repo.upsert_answer.call_args
        assert upsert_call.args[1] == "best_achievement"

    @pytest.mark.asyncio
    async def test_without_question_key_generates_all_pending(self):
        from src.worker.tasks.interview_qa import _generate_qa_async

        session = AsyncMock()
        session.commit = AsyncMock()
        sf = _make_session_factory(session)

        mock_cb = MagicMock()
        mock_cb.is_call_allowed.return_value = True

        fake_experience = MagicMock(company_name="Acme", stack="Python")
        mock_we_repo = AsyncMock()
        mock_we_repo.get_active_by_user = AsyncMock(return_value=[fake_experience])

        mock_qa_repo = AsyncMock()
        mock_qa_repo.get_ai_generated = AsyncMock(return_value=[])
        mock_qa_repo.upsert_answer = AsyncMock()

        mock_bot = AsyncMock()
        mock_bot.session = AsyncMock()

        raw_response = (
            "[QAStart]:best_achievement\nAnswer 1.[QAEnd]:best_achievement\n"
            "[QAStart]:worst_achievement\nAnswer 2.[QAEnd]:worst_achievement"
        )

        mock_ai_client = MagicMock()
        mock_ai_client.generate_text = AsyncMock(return_value=raw_response)

        mock_task = _make_mock_task(mock_cb=mock_cb, mock_bot=mock_bot)

        _we_path = "src.repositories.work_experience.WorkExperienceRepository"
        _qa_path = "src.repositories.interview_qa.StandardQuestionRepository"
        with (
            patch(_we_path, return_value=mock_we_repo),
            patch(_qa_path, return_value=mock_qa_repo),
            patch("src.services.ai.client.AIClient", return_value=mock_ai_client),
            patch("src.config.settings", bot_token="fake"),
            patch("src.core.i18n.get_text", side_effect=lambda key, locale, **kw: key),
            patch(
                "src.services.ai.prompts.build_standard_qa_system_prompt",
                return_value="system prompt",
            ),
            patch(
                "src.services.ai.prompts.build_standard_qa_user_content",
                return_value="user content",
            ),
        ):
            result = await _generate_qa_async(mock_task, sf, 1, 100, 200, "en", None)

        assert result["status"] == "completed"
        assert mock_qa_repo.upsert_answer.call_count == 2

    @pytest.mark.asyncio
    async def test_circuit_open_returns_early(self):
        from src.worker.tasks.interview_qa import _generate_qa_async

        session = AsyncMock()
        sf = _make_session_factory(session)

        mock_cb = MagicMock()
        mock_cb.is_call_allowed.return_value = False

        mock_task = _make_mock_task(mock_cb=mock_cb)

        result = await _generate_qa_async(mock_task, sf, 1, 100, 200, "en", None)

        assert result == {"status": "circuit_open"}

    @pytest.mark.asyncio
    async def test_already_generated_skips_generation(self):
        from src.models.interview_qa import BASE_QUESTION_KEYS
        from src.worker.tasks.interview_qa import _generate_qa_async

        session = AsyncMock()
        session.commit = AsyncMock()
        sf = _make_session_factory(session)

        mock_cb = MagicMock()
        mock_cb.is_call_allowed.return_value = True

        all_ai_keys = [k for k in BASE_QUESTION_KEYS if k != "why_new_job"]
        existing_questions = [_make_question(k) for k in all_ai_keys]

        mock_we_repo = AsyncMock()
        mock_we_repo.get_active_by_user = AsyncMock(return_value=[])

        mock_qa_repo = AsyncMock()
        mock_qa_repo.get_ai_generated = AsyncMock(return_value=existing_questions)

        mock_bot = AsyncMock()
        mock_bot.session = AsyncMock()

        mock_task = _make_mock_task(mock_cb=mock_cb, mock_bot=mock_bot)

        _we_path = "src.repositories.work_experience.WorkExperienceRepository"
        _qa_path = "src.repositories.interview_qa.StandardQuestionRepository"
        with (
            patch(_we_path, return_value=mock_we_repo),
            patch(_qa_path, return_value=mock_qa_repo),
            patch("src.config.settings", bot_token="fake"),
            patch("src.core.i18n.get_text", side_effect=lambda key, locale, **kw: key),
        ):
            result = await _generate_qa_async(mock_task, sf, 1, 100, 200, "en", None)

        assert result == {"status": "already_generated"}


# ── Add to Interview Flow ─────────────────────────────────────────────────────


def _make_state() -> MagicMock:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.update_data = AsyncMock()
    return state


class TestQuestionDetailKeyboard:
    def test_includes_add_to_interview_button(self):
        from src.bot.modules.interview_qa.keyboards import question_detail_keyboard

        kb = question_detail_keyboard("best_achievement", _make_i18n())
        button_texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert any("Add to interview" in t for t in button_texts)

    def test_add_to_interview_callback_has_action_and_question_key(self):
        from src.bot.modules.interview_qa.keyboards import question_detail_keyboard

        kb = question_detail_keyboard("worst_achievement", _make_i18n())
        all_data = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        add_btn_data = next(cd for cd in all_data if cd and "add_to_interview" in cd)
        assert "worst_achievement" in add_btn_data


class TestInterviewAddSelectKeyboard:
    def test_empty_list_shows_only_back_button(self):
        from src.bot.modules.interview_qa.keyboards import interview_add_select_keyboard

        kb = interview_add_select_keyboard([], 0, 0, _make_i18n())
        assert len(kb.inline_keyboard) == 1
        assert "add_to_interview_back" in kb.inline_keyboard[0][0].callback_data

    def test_interviews_listed_with_select_action(self):
        from datetime import datetime

        from src.bot.modules.interview_qa.keyboards import interview_add_select_keyboard
        from src.models.interview import Interview

        interview = MagicMock(spec=Interview)
        interview.id = 5
        interview.vacancy_title = "Python Dev"
        interview.created_at = datetime(2025, 3, 15)

        kb = interview_add_select_keyboard([interview], 0, 1, _make_i18n())
        select_btns = [
            btn
            for row in kb.inline_keyboard
            for btn in row
            if btn.callback_data and "add_to_interview_select" in btn.callback_data
        ]
        assert len(select_btns) == 1
        assert "5" in select_btns[0].callback_data


class TestHandleAddToInterview:
    @pytest.mark.asyncio
    async def test_shows_alert_when_no_fsm_data(self):
        from src.bot.modules.interview_qa.handlers import handle_add_to_interview

        callback = _make_callback()
        user = _make_user()
        state = _make_state()
        state.get_data = AsyncMock(return_value={})
        session = _make_session()
        i18n = _make_i18n()

        await handle_add_to_interview(callback, user, state, session, i18n)

        callback.answer.assert_called_once()
        assert callback.answer.call_args.kwargs.get("show_alert") is True
        callback.message.edit_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_shows_interview_list_when_fsm_data_exists(self):
        from src.bot.modules.interview_qa.handlers import handle_add_to_interview

        callback = _make_callback()
        user = _make_user()
        state = _make_state()
        state.get_data = AsyncMock(
            return_value={
                "iqa_add_question": "Q?",
                "iqa_add_answer": "A",
                "iqa_add_prev_action": "view_question",
                "iqa_add_prev_question_key": "best_achievement",
                "iqa_add_prev_reason": "",
            }
        )
        session = _make_session()
        i18n = _make_i18n()

        mock_interviews = []
        mock_get_paginated = AsyncMock(return_value=(mock_interviews, 0))

        with patch(
            "src.bot.modules.interviews.services.get_interviews_paginated",
            mock_get_paginated,
        ):
            await handle_add_to_interview(callback, user, state, session, i18n)

        mock_get_paginated.assert_called_once_with(session, user.id, 0)
        callback.message.edit_text.assert_called_once()


class TestHandleAddToInterviewSelect:
    @pytest.mark.asyncio
    async def test_creates_note_and_returns_to_list(self):
        from src.bot.modules.interview_qa.callbacks import InterviewQACallback
        from src.bot.modules.interview_qa.handlers import handle_add_to_interview_select

        callback = _make_callback()
        callback_data = InterviewQACallback(
            action="add_to_interview_select", interview_id=7
        )
        user = _make_user(user_id=1)
        state = _make_state()
        state.get_data = AsyncMock(
            return_value={
                "iqa_add_question": "Question?",
                "iqa_add_answer": "Answer.",
            }
        )
        session = _make_session()
        i18n = _make_i18n()

        mock_interview = MagicMock()
        mock_interview.user_id = 1

        mock_interview_repo = AsyncMock()
        mock_interview_repo.get_by_id = AsyncMock(return_value=mock_interview)

        mock_notes_repo = AsyncMock()
        mock_notes_repo.get_by_interview = AsyncMock(return_value=[])
        mock_notes_repo.create_note = AsyncMock()

        mock_qa_repo = AsyncMock()
        mock_qa_repo.get_ai_generated = AsyncMock(return_value=[])

        with (
            patch(
                "src.repositories.interview.InterviewRepository",
                return_value=mock_interview_repo,
            ),
            patch(
                "src.repositories.interview.InterviewNoteRepository",
                return_value=mock_notes_repo,
            ),
            patch(
                "src.bot.modules.interview_qa.handlers.StandardQuestionRepository",
                return_value=mock_qa_repo,
            ),
        ):
            await handle_add_to_interview_select(
                callback, callback_data, user, state, session, i18n
            )

        mock_notes_repo.create_note.assert_called_once()
        call_kwargs = mock_notes_repo.create_note.call_args.kwargs
        assert call_kwargs["interview_id"] == 7
        assert "Q: Question?" in call_kwargs["content"]
        assert "A: Answer." in call_kwargs["content"]
        session.commit.assert_called_once()
        callback.answer.assert_called_once()
        callback.message.edit_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_shows_alert_when_interview_not_owned_by_user(self):
        from src.bot.modules.interview_qa.callbacks import InterviewQACallback
        from src.bot.modules.interview_qa.handlers import handle_add_to_interview_select

        callback = _make_callback()
        callback_data = InterviewQACallback(
            action="add_to_interview_select", interview_id=99
        )
        user = _make_user(user_id=1)
        state = _make_state()
        state.get_data = AsyncMock(
            return_value={
                "iqa_add_question": "Q",
                "iqa_add_answer": "A",
            }
        )
        session = _make_session()
        i18n = _make_i18n()

        mock_interview = MagicMock()
        mock_interview.user_id = 999

        mock_interview_repo = AsyncMock()
        mock_interview_repo.get_by_id = AsyncMock(return_value=mock_interview)

        with patch(
            "src.repositories.interview.InterviewRepository",
            return_value=mock_interview_repo,
        ):
            await handle_add_to_interview_select(
                callback, callback_data, user, state, session, i18n
            )

        callback.answer.assert_called_once()
        assert callback.answer.call_args.kwargs.get("show_alert") is True
