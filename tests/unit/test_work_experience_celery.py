"""Unit tests for work experience AI generation via Celery.

Covers:
- _generate_async: create and edit modes, circuit breaker, AI failure
- handle_accept_draft: FSM continuation for achievements and duties,
  graceful fallback when draft row is missing
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.i18n import I18nContext

# ── Shared helpers ────────────────────────────────────────────────────────────


def _make_session() -> MagicMock:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    return session


def _make_session_factory(session):
    @asynccontextmanager
    async def _factory():
        yield session

    return _factory


def _make_user(user_id: int = 1, language_code: str = "ru") -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.language_code = language_code
    return u


def _make_callback(chat_id: int = 1, message_id: int = 10) -> AsyncMock:
    cb = AsyncMock()
    cb.message = AsyncMock()
    cb.message.chat = MagicMock()
    cb.message.chat.id = chat_id
    cb.message.message_id = message_id
    wait_msg = MagicMock()
    wait_msg.message_id = 20
    cb.message.edit_text = AsyncMock(return_value=wait_msg)
    cb.message.answer = AsyncMock()
    return cb


_GENERATED_TEXT = "• Built feature X\n• Improved Y by 30%"

_CREATE_KWARGS = dict(
    user_id=1,
    chat_id=42,
    message_id=10,
    field="achievements",
    mode="create",
    locale="ru",
    company_name="ACME",
    title="Engineer",
    stack="Python",
    period="2020-2023",
    return_to="menu",
    work_exp_id=None,
)

_EDIT_KWARGS = dict(
    user_id=1,
    chat_id=42,
    message_id=10,
    field="achievements",
    mode="edit",
    locale="ru",
    company_name="",
    title=None,
    stack="",
    period=None,
    return_to="detail",
    work_exp_id=5,
)

# All these names are locally imported inside _generate_async so patch at source.
_CB_PATH = "src.worker.circuit_breaker.CircuitBreaker"
_AI_PATH = "src.services.ai.client.AIClient"
_DRAFT_REPO_PATH = "src.repositories.work_experience_ai_draft.WorkExperienceAiDraftRepository"
_WE_REPO_PATH = "src.repositories.work_experience.WorkExperienceRepository"
_TASK_PATH = "src.worker.tasks.work_experience"

# ── Task: create mode ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_mode_generates_and_saves_draft():
    """In create mode, generated text is upserted into the draft table."""
    from src.worker.tasks.work_experience import _generate_async

    session = _make_session()
    session_factory = _make_session_factory(session)

    mock_draft_repo = AsyncMock()
    mock_cb = MagicMock()
    mock_cb.is_call_allowed.return_value = True

    with (
        patch(_CB_PATH, return_value=mock_cb),
        patch(_AI_PATH) as mock_ai_cls,
        patch(_DRAFT_REPO_PATH, return_value=mock_draft_repo),
        patch(f"{_TASK_PATH}._notify_user_create", AsyncMock()),
    ):
        mock_ai = MagicMock()
        mock_ai.generate_text = AsyncMock(return_value=_GENERATED_TEXT)
        mock_ai_cls.return_value = mock_ai

        result = await _generate_async(session_factory, **_CREATE_KWARGS)

    assert result["status"] == "completed"
    mock_draft_repo.upsert.assert_awaited_once_with(1, "achievements", _GENERATED_TEXT)
    mock_cb.record_success.assert_called_once()


@pytest.mark.asyncio
async def test_create_mode_circuit_open_returns_early():
    """When the circuit breaker is open, the task exits without calling AI."""
    from src.worker.tasks.work_experience import _generate_async

    session_factory = _make_session_factory(_make_session())
    mock_cb = MagicMock()
    mock_cb.is_call_allowed.return_value = False

    with (
        patch(_CB_PATH, return_value=mock_cb),
        patch(_AI_PATH) as mock_ai_cls,
    ):
        result = await _generate_async(session_factory, **_CREATE_KWARGS)

    assert result == {"status": "circuit_open"}
    mock_ai_cls.assert_not_called()


@pytest.mark.asyncio
async def test_create_mode_ai_failure_records_failure_and_reraises():
    """AI error triggers record_failure and propagates the exception."""
    from src.worker.tasks.work_experience import _generate_async

    session_factory = _make_session_factory(_make_session())
    mock_cb = MagicMock()
    mock_cb.is_call_allowed.return_value = True

    with (
        patch(_CB_PATH, return_value=mock_cb),
        patch(_AI_PATH) as mock_ai_cls,
    ):
        mock_ai = MagicMock()
        mock_ai.generate_text = AsyncMock(side_effect=RuntimeError("timeout"))
        mock_ai_cls.return_value = mock_ai

        with pytest.raises(RuntimeError, match="timeout"):
            await _generate_async(session_factory, **_CREATE_KWARGS)

    mock_cb.record_failure.assert_called_once()


# ── Task: edit mode ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_edit_mode_generates_and_saves_to_db():
    """In edit mode, generated text is saved directly to UserWorkExperience."""
    from src.worker.tasks.work_experience import _generate_async

    exp = MagicMock()
    exp.user_id = 1
    exp.company_name = "Corp"
    exp.title = "Dev"
    exp.stack = "Python"
    exp.period = "2021-2023"

    session = _make_session()
    session_factory = _make_session_factory(session)

    mock_we_repo = AsyncMock()
    mock_we_repo.get_by_id = AsyncMock(return_value=exp)
    mock_cb = MagicMock()
    mock_cb.is_call_allowed.return_value = True

    with (
        patch(_CB_PATH, return_value=mock_cb),
        patch(_AI_PATH) as mock_ai_cls,
        patch(_WE_REPO_PATH, return_value=mock_we_repo),
        patch(f"{_TASK_PATH}._notify_user_edit", AsyncMock()),
    ):
        mock_ai = MagicMock()
        mock_ai.generate_text = AsyncMock(return_value=_GENERATED_TEXT)
        mock_ai_cls.return_value = mock_ai

        result = await _generate_async(session_factory, **_EDIT_KWARGS)

    assert result["status"] == "completed"
    mock_we_repo.update.assert_awaited_once_with(exp, achievements=_GENERATED_TEXT)
    mock_cb.record_success.assert_called_once()


@pytest.mark.asyncio
async def test_edit_mode_with_reference_text_includes_wrapped_block_in_user_prompt():
    """Edit mode passes reference_text into the prompt shown to the model."""
    from src.worker.tasks.work_experience import _generate_async

    exp = MagicMock()
    exp.user_id = 1
    exp.company_name = "Corp"
    exp.title = "Dev"
    exp.stack = "Python"
    exp.period = "2021-2023"
    exp.achievements = "- Shipped feature X"
    exp.duties = "- Разрабатывал сервисы"

    session = _make_session()
    session_factory = _make_session_factory(session)

    mock_we_repo = AsyncMock()
    mock_we_repo.get_by_id = AsyncMock(return_value=exp)
    mock_cb = MagicMock()
    mock_cb.is_call_allowed.return_value = True

    edit_with_ref = {**_EDIT_KWARGS, "reference_text": "Notes: led migration to Postgres."}

    with (
        patch(_CB_PATH, return_value=mock_cb),
        patch(_AI_PATH) as mock_ai_cls,
        patch(_WE_REPO_PATH, return_value=mock_we_repo),
        patch(f"{_TASK_PATH}._notify_user_edit", AsyncMock()),
    ):
        mock_ai = MagicMock()
        mock_ai.generate_text = AsyncMock(return_value=_GENERATED_TEXT)
        mock_ai_cls.return_value = mock_ai

        await _generate_async(session_factory, **edit_with_ref)

    mock_ai.generate_text.assert_awaited_once()
    user_prompt = mock_ai.generate_text.call_args[0][0]
    assert "<reference_text>" in user_prompt
    assert "Notes: led migration to Postgres." in user_prompt
    assert "[ДАННЫЕ ЗАПИСИ ИЗ БД]" in user_prompt
    assert "<existing_duties>" in user_prompt
    assert "Разрабатывал сервисы" in user_prompt
    assert "<existing_achievements>" in user_prompt
    assert "Shipped feature X" in user_prompt


@pytest.mark.asyncio
async def test_edit_mode_not_found_returns_early():
    """If the work experience row is missing, the task exits without generating."""
    from src.worker.tasks.work_experience import _generate_async

    session = _make_session()
    session_factory = _make_session_factory(session)

    mock_we_repo = AsyncMock()
    mock_we_repo.get_by_id = AsyncMock(return_value=None)
    mock_cb = MagicMock()
    mock_cb.is_call_allowed.return_value = True

    with (
        patch(_CB_PATH, return_value=mock_cb),
        patch(_AI_PATH) as mock_ai_cls,
        patch(_WE_REPO_PATH, return_value=mock_we_repo),
    ):
        result = await _generate_async(session_factory, **_EDIT_KWARGS)

    assert result == {"status": "not_found"}
    mock_ai_cls.assert_not_called()


# ── Handler: handle_accept_draft ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_accept_draft_achievements_updates_fsm_and_shows_duties_prompt():
    """Accepting an achievements draft stores it in FSM and asks for duties."""
    from src.bot.modules.work_experience.callbacks import WorkExpCallback
    from src.bot.modules.work_experience.handlers import handle_accept_draft

    draft = MagicMock()
    draft.generated_text = _GENERATED_TEXT

    mock_draft_repo = AsyncMock()
    mock_draft_repo.get = AsyncMock(return_value=draft)

    callback = _make_callback()
    callback_data = WorkExpCallback(action="accept_draft", field="achievements", return_to="menu")
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"we_company_name": "ACME", "we_return_to": "menu"})
    session = _make_session()
    user = _make_user()
    i18n = I18nContext(locale="en")

    with patch(
        "src.bot.modules.work_experience.handlers.WorkExperienceAiDraftRepository",
        return_value=mock_draft_repo,
    ):
        await handle_accept_draft(callback, callback_data, user, state, session, i18n)

    state.update_data.assert_awaited_once_with(we_achievements=_GENERATED_TEXT)
    state.set_state.assert_awaited_once()
    assert callback.message.answer.call_count == 2


@pytest.mark.asyncio
async def test_handle_accept_draft_duties_calls_finish_creation():
    """Accepting a duties draft stores it in FSM and triggers _finish_work_experience_creation."""
    from src.bot.modules.work_experience.callbacks import WorkExpCallback
    from src.bot.modules.work_experience.handlers import handle_accept_draft

    draft = MagicMock()
    draft.generated_text = _GENERATED_TEXT

    mock_draft_repo = AsyncMock()
    mock_draft_repo.get = AsyncMock(return_value=draft)

    callback = _make_callback()
    callback_data = WorkExpCallback(action="accept_draft", field="duties", return_to="menu")
    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "we_company_name": "ACME",
            "we_title": "Dev",
            "we_period": "2020-2023",
            "we_stack": "Python",
            "we_achievements": "Great stuff",
            "we_duties": None,
            "we_return_to": "menu",
        }
    )
    session = _make_session()
    user = _make_user()
    i18n = I18nContext(locale="en")

    _finish_path = "src.bot.modules.work_experience.handlers._finish_work_experience_creation"
    with (
        patch(
            "src.bot.modules.work_experience.handlers.WorkExperienceAiDraftRepository",
            return_value=mock_draft_repo,
        ),
        patch(_finish_path, new_callable=AsyncMock) as mock_finish,
    ):
        await handle_accept_draft(callback, callback_data, user, state, session, i18n)

    state.update_data.assert_awaited_once_with(we_duties=_GENERATED_TEXT)
    mock_finish.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_accept_draft_missing_draft_uses_none_text():
    """When no draft row exists, the accepted text is None (treated as skipped)."""
    from src.bot.modules.work_experience.callbacks import WorkExpCallback
    from src.bot.modules.work_experience.handlers import handle_accept_draft

    mock_draft_repo = AsyncMock()
    mock_draft_repo.get = AsyncMock(return_value=None)

    callback = _make_callback()
    callback_data = WorkExpCallback(action="accept_draft", field="achievements", return_to="menu")
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"we_company_name": "ACME", "we_return_to": "menu"})
    session = _make_session()
    user = _make_user()
    i18n = I18nContext(locale="en")

    with patch(
        "src.bot.modules.work_experience.handlers.WorkExperienceAiDraftRepository",
        return_value=mock_draft_repo,
    ):
        await handle_accept_draft(callback, callback_data, user, state, session, i18n)

    state.update_data.assert_awaited_once_with(we_achievements=None)
    mock_draft_repo.delete.assert_not_awaited()
