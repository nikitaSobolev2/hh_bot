"""Unit tests for work_experience edit-mode handlers and state-filter correctness.

Bug 2: handle_generate_ai and handle_skip_field were registered without state
filters, making them match ALL states — including WorkExpForm.edit_achievements
and WorkExpForm.edit_duties.  This shadowed the dedicated edit-mode handlers
and caused KeyError / empty-AI-context in edit flows.

Fix: both creation-mode handlers now carry StateFilter restrictions so the
edit-mode handlers are actually reachable by the aiogram dispatcher.

These tests verify:
1. The creation-mode handler decorators carry the correct StateFilter so that
   edit states are excluded.
2. The edit-mode handlers (handle_edit_skip_achievements, handle_edit_skip_duties,
   handle_edit_generate_ai_achievements, handle_edit_generate_ai_duties) work
   correctly with edit-mode FSM state data.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.i18n import I18nContext

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_i18n() -> I18nContext:
    return I18nContext(locale="en")


def _make_callback() -> AsyncMock:
    callback = AsyncMock()
    callback.message = AsyncMock()
    callback.message.chat = MagicMock()
    callback.message.chat.id = 42
    callback.message.message_id = 10
    return callback


def _make_user(user_id: int = 1) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.language_code = "en"
    return user


def _make_edit_state(work_exp_id: int = 5, return_to: str = "menu") -> AsyncMock:
    """FSM state as it exists during an edit operation."""
    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "we_editing_id": work_exp_id,
            "we_editing_field": "achievements",
            "we_return_to": return_to,
        }
    )
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state


def _make_work_exp(
    exp_id: int = 5,
    user_id: int = 1,
    company_name: str = "Acme",
    stack: str = "Python",
) -> MagicMock:
    exp = MagicMock()
    exp.id = exp_id
    exp.user_id = user_id
    exp.company_name = company_name
    exp.stack = stack
    exp.title = "Developer"
    exp.period = "2020–2023"
    exp.is_active = True
    return exp


def _make_session() -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    return session


# ── State filter correctness ──────────────────────────────────────────────────


def _get_state_filter_states(handler_name: str) -> set[str]:
    """Return the set of state strings registered on a named callback handler.

    In aiogram v3 each registered handler is a HandlerObject whose `filters`
    attribute is a list of FilterObject wrappers.  The actual aiogram filter
    lives in FilterObject.callback; we extract the StateFilter from there.
    """
    from aiogram.filters.state import StateFilter

    from src.bot.modules.work_experience.handlers import router

    matched = [
        h
        for h in router.callback_query.handlers
        if getattr(h.callback, "__name__", "") == handler_name
    ]
    assert matched, f"{handler_name!r} must be registered on the router"

    handler = matched[0]
    state_filters = [f.callback for f in handler.filters if isinstance(f.callback, StateFilter)]
    assert state_filters, f"{handler_name!r} must carry a StateFilter"

    return {s.state for sf in state_filters for s in sf.states}


def test_handle_generate_ai_excludes_edit_states():
    """handle_generate_ai must NOT match edit_achievements or edit_duties states.

    The fix adds StateFilter(WorkExpForm.achievements, WorkExpForm.duties) to
    the decorator, restricting it to creation-only states.
    """
    from src.bot.modules.work_experience.states import WorkExpForm

    allowed = _get_state_filter_states("handle_generate_ai")

    assert WorkExpForm.achievements.state in allowed
    assert WorkExpForm.duties.state in allowed
    assert WorkExpForm.edit_achievements.state not in allowed
    assert WorkExpForm.edit_duties.state not in allowed


def test_handle_skip_field_excludes_edit_states():
    """handle_skip_field must NOT match edit_achievements or edit_duties states."""
    from src.bot.modules.work_experience.states import WorkExpForm

    allowed = _get_state_filter_states("handle_skip_field")

    assert WorkExpForm.title.state in allowed
    assert WorkExpForm.period.state in allowed
    assert WorkExpForm.achievements.state in allowed
    assert WorkExpForm.duties.state in allowed
    assert WorkExpForm.edit_achievements.state not in allowed
    assert WorkExpForm.edit_duties.state not in allowed


# ── Edit-mode handler behaviour ───────────────────────────────────────────────


class TestHandleEditSkipAchievements:
    @pytest.mark.asyncio
    async def test_clears_state_and_shows_detail(self):
        from src.bot.modules.work_experience.callbacks import WorkExpCallback
        from src.bot.modules.work_experience.handlers import (
            handle_edit_skip_achievements,
        )

        callback = _make_callback()
        callback_data = WorkExpCallback(
            action="skip_field", field="achievements", work_exp_id=5, return_to="menu"
        )
        user = _make_user()
        state = _make_edit_state(work_exp_id=5)
        session = _make_session()
        i18n = _make_i18n()

        exp = _make_work_exp()
        mock_repo = AsyncMock()
        mock_repo.get_by_id = AsyncMock(return_value=exp)

        with patch(
            "src.repositories.work_experience.WorkExperienceRepository",
            return_value=mock_repo,
        ):
            await handle_edit_skip_achievements(callback, callback_data, user, state, session, i18n)

        state.clear.assert_called_once()
        callback.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_call_finish_creation(self):
        """Ensure the creation-flow finaliser is never invoked from edit skip."""
        from src.bot.modules.work_experience.callbacks import WorkExpCallback
        from src.bot.modules.work_experience.handlers import (
            handle_edit_skip_achievements,
        )

        callback = _make_callback()
        callback_data = WorkExpCallback(
            action="skip_field", field="achievements", work_exp_id=5, return_to="menu"
        )
        user = _make_user()
        state = _make_edit_state(work_exp_id=5)
        session = _make_session()
        i18n = _make_i18n()

        exp = _make_work_exp()
        mock_repo = AsyncMock()
        mock_repo.get_by_id = AsyncMock(return_value=exp)

        with (
            patch(
                "src.repositories.work_experience.WorkExperienceRepository",
                return_value=mock_repo,
            ),
            patch(
                "src.bot.modules.work_experience.handlers._finish_work_experience_creation"
            ) as mock_finish,
        ):
            await handle_edit_skip_achievements(callback, callback_data, user, state, session, i18n)

        mock_finish.assert_not_called()


class TestHandleEditSkipDuties:
    @pytest.mark.asyncio
    async def test_clears_state_and_shows_detail(self):
        from src.bot.modules.work_experience.callbacks import WorkExpCallback
        from src.bot.modules.work_experience.handlers import handle_edit_skip_duties

        callback = _make_callback()
        callback_data = WorkExpCallback(
            action="skip_field", field="duties", work_exp_id=5, return_to="menu"
        )
        user = _make_user()
        state = _make_edit_state(work_exp_id=5)
        session = _make_session()
        i18n = _make_i18n()

        exp = _make_work_exp()
        mock_repo = AsyncMock()
        mock_repo.get_by_id = AsyncMock(return_value=exp)

        with patch(
            "src.repositories.work_experience.WorkExperienceRepository",
            return_value=mock_repo,
        ):
            await handle_edit_skip_duties(callback, callback_data, user, state, session, i18n)

        state.clear.assert_called_once()
        callback.answer.assert_called_once()


class TestHandleEditGenerateAiAchievements:
    @pytest.mark.asyncio
    async def test_generates_from_db_and_saves(self):
        """Edit-mode AI generation reads exp from DB, not from FSM state."""
        from src.bot.modules.work_experience.callbacks import WorkExpCallback
        from src.bot.modules.work_experience.handlers import (
            handle_edit_generate_ai_achievements,
        )

        callback = _make_callback()
        callback_data = WorkExpCallback(
            action="generate_ai",
            field="achievements",
            work_exp_id=5,
            return_to="menu",
        )
        user = _make_user()
        state = _make_edit_state(work_exp_id=5)
        session = _make_session()
        i18n = _make_i18n()

        exp = _make_work_exp()
        mock_repo = AsyncMock()
        mock_repo.get_by_id = AsyncMock(return_value=exp)
        mock_repo.update = AsyncMock()
        mock_task = MagicMock()

        with (
            patch(
                "src.repositories.work_experience.WorkExperienceRepository",
                return_value=mock_repo,
            ),
            patch(
                "src.worker.tasks.work_experience.generate_work_experience_ai_task",
                mock_task,
            ),
        ):
            await handle_edit_generate_ai_achievements(
                callback, callback_data, user, state, session, i18n
            )

        mock_task.delay.assert_called_once()
        state.clear.assert_called_once()
        callback.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_shows_alert_and_returns_when_exp_not_found(self):
        from src.bot.modules.work_experience.callbacks import WorkExpCallback
        from src.bot.modules.work_experience.handlers import (
            handle_edit_generate_ai_achievements,
        )

        callback = _make_callback()
        callback_data = WorkExpCallback(
            action="generate_ai",
            field="achievements",
            work_exp_id=99,
            return_to="menu",
        )
        user = _make_user()
        state = _make_edit_state(work_exp_id=99)
        session = _make_session()
        i18n = _make_i18n()

        mock_repo = AsyncMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)
        mock_task = MagicMock()

        with (
            patch(
                "src.repositories.work_experience.WorkExperienceRepository",
                return_value=mock_repo,
            ),
            patch(
                "src.worker.tasks.work_experience.generate_work_experience_ai_task",
                mock_task,
            ),
        ):
            await handle_edit_generate_ai_achievements(
                callback, callback_data, user, state, session, i18n
            )

        mock_task.delay.assert_not_called()
        callback.answer.assert_called_once()
        assert callback.answer.call_args.kwargs.get("show_alert") is True


class TestHandleEditGenerateAiDuties:
    @pytest.mark.asyncio
    async def test_generates_from_db_and_saves(self):
        """Edit-mode duties AI generation reads exp from DB, not from FSM state."""
        from src.bot.modules.work_experience.callbacks import WorkExpCallback
        from src.bot.modules.work_experience.handlers import (
            handle_edit_generate_ai_duties,
        )

        callback = _make_callback()
        callback_data = WorkExpCallback(
            action="generate_ai",
            field="duties",
            work_exp_id=5,
            return_to="menu",
        )
        user = _make_user()
        state = _make_edit_state(work_exp_id=5)
        session = _make_session()
        i18n = _make_i18n()

        exp = _make_work_exp()
        mock_repo = AsyncMock()
        mock_repo.get_by_id = AsyncMock(return_value=exp)
        mock_repo.update = AsyncMock()
        mock_task = MagicMock()

        with (
            patch(
                "src.repositories.work_experience.WorkExperienceRepository",
                return_value=mock_repo,
            ),
            patch(
                "src.worker.tasks.work_experience.generate_work_experience_ai_task",
                mock_task,
            ),
        ):
            await handle_edit_generate_ai_duties(
                callback, callback_data, user, state, session, i18n
            )

        mock_task.delay.assert_called_once()
        state.clear.assert_called_once()
        callback.answer.assert_called_once()
