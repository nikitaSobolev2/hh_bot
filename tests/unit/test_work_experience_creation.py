"""Unit tests for the extended Work Experience creation FSM.

Tests verify that:
- fsm_stack transitions to the achievements state (no longer saves to DB directly)
- fsm_achievements stores typed text and advances to the duties state
- handle_skip_field stores None and advances to the correct next state
- _finish_work_experience_creation calls add_work_experience with all four fields
- add_work_experience service passes achievements and duties to the repository
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session


def _make_state(data: dict | None = None) -> AsyncMock:
    state = AsyncMock()
    _data: dict = dict(data or {})

    async def _get_data() -> dict:
        return dict(_data)

    async def _update_data(**kwargs: object) -> None:
        _data.update(kwargs)

    state.get_data = _get_data
    state.update_data = _update_data
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state


def _make_message(text: str | None = None) -> AsyncMock:
    msg = AsyncMock()
    msg.text = text
    msg.answer = AsyncMock()
    msg.edit_text = AsyncMock()
    return msg


def _make_user(user_id: int = 1) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    return user


# ── fsm_stack transitions to achievements state ───────────────────────────────


def test_fsm_stack_does_not_save_to_db_and_advances_to_achievements_state():
    """fsm_stack must NOT save to DB — it stores stack in state and sets achievements state."""
    from src.bot.modules.work_experience.states import WorkExpForm

    state = _make_state({"we_return_to": "menu", "we_company_name": "Acme"})
    message = _make_message("Python, Django")
    user = _make_user()

    with patch("src.bot.modules.work_experience.handlers.work_exp_ai_input_keyboard") as kb_mock:
        kb_mock.return_value = MagicMock()
        asyncio.run(_call_fsm_stack(message, user, state))

    state.set_state.assert_called_once_with(WorkExpForm.achievements)
    message.answer.assert_called_once()


async def _call_fsm_stack(message, user, state) -> None:
    from src.bot.modules.work_experience.handlers import fsm_stack

    await fsm_stack(message, user, state, MagicMock())


def test_fsm_stack_stores_stack_in_state():
    """fsm_stack stores the entered stack in FSM state under we_stack."""
    stored: dict = {}

    async def _update_data(**kwargs: object) -> None:
        stored.update(kwargs)

    state = _make_state({"we_return_to": "menu", "we_company_name": "Acme"})
    state.update_data = _update_data  # type: ignore[assignment]
    state.set_state = AsyncMock()
    message = _make_message("Python, Django")
    user = _make_user()

    with patch("src.bot.modules.work_experience.handlers.work_exp_ai_input_keyboard"):
        asyncio.run(_call_fsm_stack_direct(message, user, state))

    assert stored.get("we_stack") == "Python, Django"


async def _call_fsm_stack_direct(message, user, state) -> None:
    from src.bot.modules.work_experience.handlers import fsm_stack

    await fsm_stack(message, user, state, MagicMock())


def test_fsm_stack_rejects_empty_stack():
    """fsm_stack answers with an error message when stack is empty."""
    state = _make_state({"we_return_to": "menu", "we_company_name": "Acme"})
    message = _make_message("")
    user = _make_user()
    i18n = MagicMock()
    i18n.get = MagicMock(return_value="stack invalid")

    asyncio.run(_call_fsm_stack_direct(message, user, state))

    state.set_state.assert_not_called()
    message.answer.assert_called_once()


# ── fsm_achievements advances to duties state ────────────────────────────────


def test_fsm_achievements_stores_text_and_sets_duties_state():
    """fsm_achievements saves entered text and transitions to the duties state."""
    from src.bot.modules.work_experience.states import WorkExpForm

    state = _make_state({"we_return_to": "menu", "we_company_name": "Acme"})
    message = _make_message("Increased revenue by 20%")
    user = _make_user()

    with patch("src.bot.modules.work_experience.handlers.work_exp_ai_input_keyboard"):
        asyncio.run(_run_fsm_achievements(message, user, state))

    state.set_state.assert_called_with(WorkExpForm.duties)


async def _run_fsm_achievements(message, user, state) -> None:
    from src.bot.modules.work_experience.handlers import fsm_achievements

    await fsm_achievements(message, user, state, MagicMock())


def test_fsm_achievements_stores_none_on_empty_input():
    """fsm_achievements stores None when the user sends an empty/whitespace message."""
    stored: dict = {}

    async def _update_data(**kwargs: object) -> None:
        stored.update(kwargs)

    state = _make_state({"we_return_to": "menu", "we_company_name": "Acme"})
    state.update_data = _update_data  # type: ignore[assignment]
    state.set_state = AsyncMock()
    message = _make_message("   ")
    user = _make_user()

    with patch("src.bot.modules.work_experience.handlers.work_exp_ai_input_keyboard"):
        asyncio.run(_run_fsm_achievements(message, user, state))

    assert stored.get("we_achievements") is None


# ── handle_skip_field skips achievements → advances to duties ─────────────────


def test_handle_skip_field_achievements_sets_none_and_duties_state():
    """handle_skip_field for achievements field stores None and transitions to duties."""
    from src.bot.modules.work_experience.states import WorkExpForm

    state = _make_state({"we_return_to": "menu", "we_company_name": "Acme"})
    callback = AsyncMock()
    callback.message = _make_message()
    callback.answer = AsyncMock()
    callback_data = MagicMock()
    callback_data.field = "achievements"
    callback_data.return_to = "menu"
    user = _make_user()

    with patch("src.bot.modules.work_experience.handlers.work_exp_ai_input_keyboard"):
        asyncio.run(_run_skip_field(callback, callback_data, user, state, _make_session()))

    state.set_state.assert_called_with(WorkExpForm.duties)


async def _run_skip_field(callback, callback_data, user, state, session) -> None:
    from src.bot.modules.work_experience.handlers import handle_skip_field

    await handle_skip_field(callback, callback_data, user, state, session, MagicMock())


# ── _finish_work_experience_creation calls service with all fields ────────────


def test_finish_work_experience_creation_passes_all_fields():
    """_finish_work_experience_creation calls add_work_experience with all six fields."""
    state = _make_state(
        {
            "we_return_to": "menu",
            "we_company_name": "Acme",
            "we_title": "Backend Developer",
            "we_period": "2020-2023",
            "we_stack": "Python",
            "we_achievements": "Built CI/CD pipeline",
            "we_duties": "Developed REST APIs",
        }
    )
    session = _make_session()
    message = _make_message()
    user = _make_user(user_id=7)

    with (
        patch("src.bot.modules.work_experience.handlers.we_service") as svc_mock,
        patch("src.bot.modules.work_experience.handlers.show_work_experience"),
    ):
        svc_mock.add_work_experience = AsyncMock()
        asyncio.run(_run_finish(message, user, state, session))

    svc_mock.add_work_experience.assert_called_once_with(
        session,
        7,
        "Acme",
        "Python",
        title="Backend Developer",
        period="2020-2023",
        achievements="Built CI/CD pipeline",
        duties="Developed REST APIs",
    )


async def _run_finish(message, user, state, session) -> None:
    from src.bot.modules.work_experience.handlers import _finish_work_experience_creation

    await _finish_work_experience_creation(message, user, state, session, MagicMock())


def test_finish_work_experience_creation_passes_none_when_optional_fields_skipped():
    """_finish_work_experience_creation passes None for all optional fields when skipped."""
    state = _make_state(
        {
            "we_return_to": "menu",
            "we_company_name": "Acme",
            "we_stack": "Go",
        }
    )
    session = _make_session()
    message = _make_message()
    user = _make_user(user_id=3)

    with (
        patch("src.bot.modules.work_experience.handlers.we_service") as svc_mock,
        patch("src.bot.modules.work_experience.handlers.show_work_experience"),
    ):
        svc_mock.add_work_experience = AsyncMock()
        asyncio.run(_run_finish(message, user, state, session))

    svc_mock.add_work_experience.assert_called_once_with(
        session,
        3,
        "Acme",
        "Go",
        title=None,
        period=None,
        achievements=None,
        duties=None,
    )


# ── add_work_experience service passes new fields to repository ───────────────


def test_add_work_experience_service_passes_all_fields_to_repo():
    """add_work_experience service forwards all six fields to repository.create."""
    from src.bot.modules.parsing.services import add_work_experience

    session = _make_session()

    created_experience: dict = {}

    async def _mock_create(**kwargs: object):
        created_experience.update(kwargs)
        return MagicMock()

    with patch("src.bot.modules.parsing.services.WorkExperienceRepository") as repo_cls:
        repo_instance = MagicMock()
        repo_instance.create = _mock_create
        repo_cls.return_value = repo_instance

        asyncio.run(
            add_work_experience(
                session,
                user_id=5,
                company_name="StartupX",
                stack="React, Node.js",
                title="Frontend Developer",
                period="2021-2024",
                achievements="Shipped MVP in 2 months",
                duties="Led frontend development",
            )
        )

    assert created_experience["title"] == "Frontend Developer"
    assert created_experience["period"] == "2021-2024"
    assert created_experience["achievements"] == "Shipped MVP in 2 months"
    assert created_experience["duties"] == "Led frontend development"
