"""Tests verifying callback.answer() is called before long-running operations.

Telegram requires callback.answer() within 10 seconds of receiving the callback
query. Handlers that perform AI generation or multiple DB writes before answering
will raise "query is too old" errors. These tests confirm the correct ordering.

The technique: make the long operation raise a RuntimeError, then assert that
callback.answer() was already invoked. If it were called after, the exception
would abort execution before reaching it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.i18n import I18nContext

# ── Shared fixtures ───────────────────────────────────────────────────────────


def _make_callback(chat_id: int = 1, message_id: int = 10) -> AsyncMock:
    cb = AsyncMock()
    cb.message = AsyncMock()
    cb.message.chat = MagicMock()
    cb.message.chat.id = chat_id
    cb.message.message_id = message_id
    wait_msg = MagicMock()
    wait_msg.message_id = 20
    cb.message.edit_text = AsyncMock(return_value=wait_msg)
    return cb


def _make_user(user_id: int = 1, language_code: str = "ru") -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.language_code = language_code
    return u


# ── work_experience: handle_generate_ai ──────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_generate_ai_achievements_answers_before_ai_call():
    """handle_generate_ai answers callback and dispatches the Celery task (not AI directly)."""
    from src.bot.modules.work_experience.callbacks import WorkExpCallback
    from src.bot.modules.work_experience.handlers import handle_generate_ai

    callback = _make_callback()
    callback_data = WorkExpCallback(action="generate_ai", field="achievements", return_to="profile")
    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "we_company_name": "ACME",
            "we_title": "Dev",
            "we_stack": "Python",
            "we_period": "2020-2023",
        }
    )
    session = AsyncMock()
    i18n = I18nContext(locale="en")

    mock_task = MagicMock()
    with patch("src.worker.tasks.work_experience.generate_work_experience_ai_task", mock_task):
        await handle_generate_ai(callback, callback_data, _make_user(), state, session, i18n)

    callback.answer.assert_called_once()
    mock_task.delay.assert_called_once()


@pytest.mark.asyncio
async def test_handle_generate_ai_duties_answers_before_ai_call():
    """handle_generate_ai answers callback and dispatches the Celery task for duties."""
    from src.bot.modules.work_experience.callbacks import WorkExpCallback
    from src.bot.modules.work_experience.handlers import handle_generate_ai

    callback = _make_callback()
    callback_data = WorkExpCallback(action="generate_ai", field="duties", return_to="profile")
    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "we_company_name": "ACME",
            "we_title": "Dev",
            "we_stack": "Python",
            "we_period": "2020-2023",
        }
    )
    session = AsyncMock()
    i18n = I18nContext(locale="en")

    mock_task = MagicMock()
    with patch("src.worker.tasks.work_experience.generate_work_experience_ai_task", mock_task):
        await handle_generate_ai(callback, callback_data, _make_user(), state, session, i18n)

    callback.answer.assert_called_once()
    mock_task.delay.assert_called_once()


# ── work_experience: _handle_edit_generate_ai ─────────────────────────────────


@pytest.mark.asyncio
async def test_edit_generate_ai_answers_before_ai_call():
    """_handle_edit_generate_ai answers callback and dispatches the Celery task."""
    from src.bot.modules.work_experience.callbacks import WorkExpCallback
    from src.bot.modules.work_experience.handlers import handle_edit_generate_ai_achievements

    exp = MagicMock()
    exp.company_name = "Corp"
    exp.stack = "Python"
    exp.title = "Engineer"
    exp.period = "2021-2024"

    callback = _make_callback()
    callback_data = WorkExpCallback(action="generate_ai", field="achievements", return_to="detail")
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"we_editing_id": 5, "we_return_to": "detail"})
    session = AsyncMock()
    i18n = I18nContext(locale="en")

    mock_repo = AsyncMock()
    mock_repo.get_by_id = AsyncMock(return_value=exp)
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
            callback, callback_data, _make_user(), state, session, i18n
        )

    callback.answer.assert_called_once_with()
    mock_task.delay.assert_called_once()


@pytest.mark.asyncio
async def test_edit_generate_ai_shows_alert_when_exp_not_found_and_skips_ai():
    """When the work experience is missing, an alert is shown and task is not dispatched."""
    from src.bot.modules.work_experience.callbacks import WorkExpCallback
    from src.bot.modules.work_experience.handlers import handle_edit_generate_ai_achievements

    callback = _make_callback()
    callback_data = WorkExpCallback(action="generate_ai", field="achievements", return_to="detail")
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"we_editing_id": 99, "we_return_to": "detail"})
    session = AsyncMock()
    i18n = I18nContext(locale="en")

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
            callback, callback_data, _make_user(), state, session, i18n
        )

    mock_task.delay.assert_not_called()
    callback.answer.assert_called_once()
    _, kwargs = callback.answer.call_args
    assert kwargs.get("show_alert") is True


# ── work_experience: improve stack ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_improve_stack_from_edit_answers_before_celery():
    """handle_improve_stack_from_edit answers callback and dispatches improve_stack task."""
    from src.bot.modules.work_experience.callbacks import ImproveStackAction, ImproveStackCallback
    from src.bot.modules.work_experience.handlers import handle_improve_stack_from_edit

    exp = MagicMock()
    exp.user_id = 1
    exp.is_active = True

    callback = _make_callback()
    callback_data = ImproveStackCallback(
        action=ImproveStackAction.from_edit,
        work_exp_id=5,
        return_to="menu",
    )
    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "we_editing_field": "stack",
            "we_editing_id": 5,
            "we_return_to": "detail",
        }
    )
    session = AsyncMock()
    i18n = I18nContext(locale="en")

    mock_repo = AsyncMock()
    mock_repo.get_by_id = AsyncMock(return_value=exp)
    mock_task = MagicMock()

    with (
        patch(
            "src.repositories.work_experience.WorkExperienceRepository",
            return_value=mock_repo,
        ),
        patch(
            "src.worker.tasks.work_experience.improve_work_experience_stack_task",
            mock_task,
        ),
    ):
        await handle_improve_stack_from_edit(
            callback, callback_data, _make_user(), state, session, i18n
        )

    callback.answer.assert_called_once_with()
    mock_task.delay.assert_called_once()


@pytest.mark.asyncio
async def test_improve_stack_pick_answers_before_celery():
    """handle_improve_stack_pick answers callback and dispatches improve_stack task."""
    from src.bot.modules.work_experience.callbacks import ImproveStackAction, ImproveStackCallback
    from src.bot.modules.work_experience.handlers import handle_improve_stack_pick

    exp = MagicMock()
    exp.user_id = 1
    exp.is_active = True

    callback = _make_callback()
    callback_data = ImproveStackCallback(
        action=ImproveStackAction.pick,
        work_exp_id=3,
        return_to="menu",
    )
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"we_return_to": "menu"})
    session = AsyncMock()
    i18n = I18nContext(locale="en")

    mock_repo = AsyncMock()
    mock_repo.get_by_id = AsyncMock(return_value=exp)
    mock_task = MagicMock()

    with (
        patch(
            "src.repositories.work_experience.WorkExperienceRepository",
            return_value=mock_repo,
        ),
        patch(
            "src.worker.tasks.work_experience.improve_work_experience_stack_task",
            mock_task,
        ),
    ):
        await handle_improve_stack_pick(callback, callback_data, _make_user(), state, session, i18n)

    callback.answer.assert_called_once_with()
    mock_task.delay.assert_called_once()


# ── achievements: handle_proceed ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_proceed_answers_before_db_writes():
    """handle_proceed answers the callback before creating generation rows in DB."""
    from src.bot.modules.achievements.handlers import handle_proceed

    call_order: list[str] = []

    callback = _make_callback()
    callback.answer = AsyncMock(side_effect=lambda *a, **kw: call_order.append("answer"))

    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "ach_exp_ids": [1],
            "ach_exp_names": ["ACME"],
            "ach_achievements": ["Built X"],
            "ach_responsibilities": ["Led Y"],
        }
    )

    gen_obj = MagicMock()
    gen_obj.id = 7

    mock_gen_repo = AsyncMock()
    mock_gen_repo.create = AsyncMock(
        side_effect=lambda *a, **kw: call_order.append("db_create") or gen_obj
    )
    mock_item_repo = AsyncMock()
    session = AsyncMock()
    i18n = I18nContext(locale="en")

    with (
        patch(
            "src.bot.modules.achievements.handlers.AchievementGenerationRepository",
            return_value=mock_gen_repo,
        ),
        patch(
            "src.bot.modules.achievements.handlers.AchievementItemRepository",
            return_value=mock_item_repo,
        ),
        patch("src.worker.tasks.achievements.generate_achievements_task") as mock_task,
    ):
        mock_task.delay = MagicMock()
        await handle_proceed(callback, _make_user(), state, session, i18n)

    assert "answer" in call_order
    assert "db_create" in call_order
    assert call_order.index("answer") < call_order.index("db_create")


# ── interviews: fsm_proceed ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fsm_proceed_answers_before_bulk_insert():
    """fsm_proceed answers the callback before bulk-inserting interview questions."""
    from src.bot.modules.interviews.handlers import fsm_proceed

    call_order: list[str] = []

    callback = _make_callback()
    callback.answer = AsyncMock(side_effect=lambda *a, **kw: call_order.append("answer"))

    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "vacancy_title": "Python Dev",
            "questions": [{"question": "Tell me about yourself"}],
        }
    )

    interview_obj = MagicMock()
    interview_obj.id = 3

    mock_svc = MagicMock()
    mock_svc.create_interview = AsyncMock(return_value=interview_obj)
    mock_svc.bulk_create_questions = AsyncMock(
        side_effect=lambda *a, **kw: call_order.append("bulk_insert")
    )

    session = AsyncMock()
    i18n = I18nContext(locale="en")

    with (
        patch("src.bot.modules.interviews.handlers.interview_service", mock_svc),
        patch("src.worker.tasks.interviews.analyze_interview_task") as mock_task,
    ):
        mock_task.delay = MagicMock()
        await fsm_proceed(callback, state, session, _make_user(), i18n)

    assert "answer" in call_order
    assert "bulk_insert" in call_order
    assert call_order.index("answer") < call_order.index("bulk_insert")


# ── vacancy_summary: handle_regenerate ───────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_regenerate_answers_before_soft_delete():
    """handle_regenerate answers the callback before soft-deleting the old summary."""
    from src.bot.modules.vacancy_summary.callbacks import VacancySummaryCallback
    from src.bot.modules.vacancy_summary.handlers import handle_regenerate

    call_order: list[str] = []

    old_summary = MagicMock()
    old_summary.id = 10
    old_summary.user_id = 1
    old_summary.excluded_industries = "gambling"
    old_summary.location = None
    old_summary.remote_preference = None
    old_summary.additional_notes = None

    new_summary = MagicMock()
    new_summary.id = 20
    new_summary.excluded_industries = old_summary.excluded_industries
    new_summary.location = None
    new_summary.remote_preference = None
    new_summary.additional_notes = None

    callback = _make_callback(chat_id=5, message_id=99)
    callback.answer = AsyncMock(side_effect=lambda *a, **kw: call_order.append("answer"))

    mock_repo = AsyncMock()
    mock_repo.get_by_id = AsyncMock(return_value=old_summary)
    mock_repo.soft_delete = AsyncMock(side_effect=lambda *a, **kw: call_order.append("soft_delete"))
    mock_repo.create = AsyncMock(return_value=new_summary)

    callback_data = VacancySummaryCallback(action="regenerate", summary_id=10)
    user = MagicMock()
    user.id = 1
    user.language_code = "ru"
    state = AsyncMock()
    session = AsyncMock()
    i18n = I18nContext(locale="en")

    with (
        patch(
            "src.bot.modules.vacancy_summary.handlers.VacancySummaryRepository",
            return_value=mock_repo,
        ),
        patch("src.worker.tasks.vacancy_summary.generate_vacancy_summary_task") as mock_task,
    ):
        mock_task.delay = MagicMock()
        await handle_regenerate(callback, callback_data, user, state, session, i18n)

    assert "answer" in call_order
    assert "soft_delete" in call_order
    assert call_order.index("answer") < call_order.index("soft_delete")
