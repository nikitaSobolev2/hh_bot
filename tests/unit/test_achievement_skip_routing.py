"""Unit tests for achievement generation skip-input routing.

Verifies that skip_input callbacks route to the correct advance function
depending on the current ach_step stored in FSM state.

Bug being prevented:
  When a user is in the collecting_responsibilities phase, old Skip buttons
  from the collecting_achievements phase must NOT re-trigger the achievements
  advance logic — they must be ignored because the handler is now state-filtered.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_state(data: dict) -> AsyncMock:
    state = AsyncMock()
    _data = dict(data)

    async def _get_data() -> dict:
        return dict(_data)

    async def _update_data(**kwargs: object) -> None:
        _data.update(kwargs)

    state.get_data = _get_data
    state.update_data = _update_data
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state


def _make_callback(message_text: str = "question?") -> AsyncMock:
    cb = AsyncMock()
    cb.message = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _base_state_data(step: str, index: int = 0, count: int = 2) -> dict:
    return {
        "ach_exp_ids": list(range(count)),
        "ach_exp_names": [f"Company{i}" for i in range(count)],
        "ach_stacks": ["Python"] * count,
        "ach_step": step,
        "ach_index": index,
        "ach_achievements": [None] * count,
        "ach_responsibilities": [None] * count,
    }


# ── skip routes to achievements advance when step == "achievements" ───────────


def test_skip_achievements_handler_advances_to_next_achievement():
    """handle_skip_achievements calls _advance_achievements_step with current index."""
    from src.bot.modules.achievements.callbacks import AchievementCallback
    from src.bot.modules.achievements.handlers import handle_skip_achievements

    state = _make_state(_base_state_data("achievements", index=0, count=3))
    callback = _make_callback()
    callback_data = AchievementCallback(action="skip_input", item_id=0)
    user = MagicMock()

    with patch("src.bot.modules.achievements.handlers._advance_achievements_step") as advance_mock:
        advance_mock.return_value = AsyncMock()()
        asyncio.run(handle_skip_achievements(callback, callback_data, user, state, MagicMock()))

    advance_mock.assert_called_once()
    _, kwargs = advance_mock.call_args
    assert kwargs.get("edit") is True


# ── skip routes to responsibilities advance when step == "responsibilities" ───


def test_skip_responsibilities_handler_advances_to_next_responsibility():
    """handle_skip_responsibilities calls _advance_responsibilities_step with current index."""
    from src.bot.modules.achievements.callbacks import AchievementCallback
    from src.bot.modules.achievements.handlers import handle_skip_responsibilities

    state = _make_state(_base_state_data("responsibilities", index=0, count=2))
    callback = _make_callback()
    callback_data = AchievementCallback(action="skip_input", item_id=0)
    user = MagicMock()

    with patch(
        "src.bot.modules.achievements.handlers._advance_responsibilities_step"
    ) as advance_mock:
        advance_mock.return_value = AsyncMock()()
        asyncio.run(handle_skip_responsibilities(callback, callback_data, user, state, MagicMock()))

    advance_mock.assert_called_once()
    _, kwargs = advance_mock.call_args
    assert kwargs.get("edit") is True


# ── _advance_achievements_step edit flag propagates ───────────────────────────


def test_advance_achievements_step_passes_edit_flag_to_ask_for_input():
    """When edit=True, _advance_achievements_step forwards it to _ask_for_input."""
    from src.bot.modules.achievements.handlers import _advance_achievements_step

    state = _make_state(_base_state_data("achievements", index=0, count=2))
    data = _base_state_data("achievements", index=0, count=2)
    message = AsyncMock()

    with patch("src.bot.modules.achievements.handlers._ask_for_input") as ask_mock:
        ask_mock.return_value = AsyncMock()()
        asyncio.run(_advance_achievements_step(message, state, data, 0, MagicMock(), edit=True))

    ask_mock.assert_called_once()
    _, kwargs = ask_mock.call_args
    assert kwargs.get("edit") is True


def test_advance_achievements_step_transitions_to_responsibilities_at_end():
    """_advance_achievements_step transitions to collecting_responsibilities when last entry."""
    from src.bot.modules.achievements.handlers import _advance_achievements_step
    from src.bot.modules.achievements.states import AchievementForm

    state = _make_state(_base_state_data("achievements", index=1, count=2))
    data = _base_state_data("achievements", index=1, count=2)
    message = AsyncMock()

    with patch("src.bot.modules.achievements.handlers._ask_for_input") as ask_mock:
        ask_mock.return_value = AsyncMock()()
        asyncio.run(_advance_achievements_step(message, state, data, 1, MagicMock(), edit=True))

    state.set_state.assert_called_with(AchievementForm.collecting_responsibilities)


# ── _advance_responsibilities_step edit flag propagates ──────────────────────


def test_advance_responsibilities_step_passes_edit_flag_to_ask_for_input():
    """When edit=True, _advance_responsibilities_step forwards it to _ask_for_input."""
    from src.bot.modules.achievements.handlers import _advance_responsibilities_step

    state = _make_state(_base_state_data("responsibilities", index=0, count=2))
    data = _base_state_data("responsibilities", index=0, count=2)
    message = AsyncMock()

    with patch("src.bot.modules.achievements.handlers._ask_for_input") as ask_mock:
        ask_mock.return_value = AsyncMock()()
        asyncio.run(_advance_responsibilities_step(message, state, data, 0, MagicMock(), edit=True))

    ask_mock.assert_called_once()
    _, kwargs = ask_mock.call_args
    assert kwargs.get("edit") is True


def test_advance_responsibilities_step_calls_show_proceed_at_end():
    """_advance_responsibilities_step calls _show_proceed when last entry is processed."""
    from src.bot.modules.achievements.handlers import _advance_responsibilities_step

    state = _make_state(_base_state_data("responsibilities", index=1, count=2))
    data = _base_state_data("responsibilities", index=1, count=2)
    message = AsyncMock()

    with patch("src.bot.modules.achievements.handlers._show_proceed") as proceed_mock:
        proceed_mock.return_value = AsyncMock()()
        asyncio.run(_advance_responsibilities_step(message, state, data, 1, MagicMock()))

    proceed_mock.assert_called_once()


# ── handle_generate_new shows work experience view when experiences exist ─────


def test_handle_generate_new_shows_work_experience_view_when_experiences_exist():
    """handle_generate_new must show the work experience list (not start FSM) when data exists."""
    from src.bot.modules.achievements.callbacks import AchievementCallback
    from src.bot.modules.achievements.handlers import handle_generate_new

    callback = _make_callback()
    callback_data = AchievementCallback(action="generate_new")
    user = MagicMock()
    user.id = 1
    state = _make_state({})
    session = AsyncMock()
    i18n = MagicMock()

    fake_experiences = [MagicMock(), MagicMock()]

    with (
        patch(
            "src.bot.modules.parsing.services.get_active_work_experiences",
            new=AsyncMock(return_value=fake_experiences),
        ),
        patch("src.bot.modules.work_experience.handlers.show_work_experience") as show_we_mock,
    ):
        show_we_mock.return_value = AsyncMock()()
        asyncio.run(handle_generate_new(callback, callback_data, user, state, session, i18n))

    show_we_mock.assert_called_once()
    call_kwargs = show_we_mock.call_args
    assert "achievements_collect" in str(call_kwargs)
    state.set_state.assert_not_called()


def test_handle_generate_new_redirects_to_work_experience_when_no_experiences():
    """handle_generate_new redirects to work experience setup when no experiences exist."""
    from src.bot.modules.achievements.callbacks import AchievementCallback
    from src.bot.modules.achievements.handlers import handle_generate_new

    callback = _make_callback()
    callback_data = AchievementCallback(action="generate_new")
    user = MagicMock()
    user.id = 1
    state = _make_state({})
    session = AsyncMock()
    i18n = MagicMock()

    with (
        patch(
            "src.bot.modules.parsing.services.get_active_work_experiences",
            new=AsyncMock(return_value=[]),
        ),
        patch("src.bot.modules.work_experience.handlers.show_work_experience") as show_we_mock,
    ):
        show_we_mock.return_value = AsyncMock()()
        asyncio.run(handle_generate_new(callback, callback_data, user, state, session, i18n))

    show_we_mock.assert_called_once()
    call_kwargs = show_we_mock.call_args
    assert "achievements" in str(call_kwargs)
    state.set_state.assert_not_called()
