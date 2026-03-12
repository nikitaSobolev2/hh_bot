"""Unit tests for vacancy summary regenerate-with-same-params behaviour."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Repository: create persists params ────────────────────────────────────────


def _make_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


def test_repository_create_persists_all_params():
    """create() stores all four generation params on the returned row."""
    from src.repositories.vacancy_summary import VacancySummaryRepository

    session = _make_session()
    repo = VacancySummaryRepository(session)

    import asyncio

    summary = asyncio.run(
        repo.create(
            user_id=42,
            excluded_industries="gambling",
            location="Moscow",
            remote_preference="remote",
            additional_notes="Some notes",
        )
    )

    assert summary.user_id == 42
    assert summary.excluded_industries == "gambling"
    assert summary.location == "Moscow"
    assert summary.remote_preference == "remote"
    assert summary.additional_notes == "Some notes"


def test_repository_create_defaults_to_none():
    """create() without params stores all fields as None."""
    from src.repositories.vacancy_summary import VacancySummaryRepository

    session = _make_session()
    repo = VacancySummaryRepository(session)

    import asyncio

    summary = asyncio.run(repo.create(user_id=1))

    assert summary.excluded_industries is None
    assert summary.location is None
    assert summary.remote_preference is None
    assert summary.additional_notes is None


# ── Handler: handle_regenerate path selection ─────────────────────────────────


def _make_old_summary(
    user_id: int = 1,
    excluded_industries: str | None = None,
    location: str | None = None,
    remote_preference: str | None = None,
    additional_notes: str | None = None,
) -> MagicMock:
    s = MagicMock()
    s.id = 99
    s.user_id = user_id
    s.is_deleted = False
    s.excluded_industries = excluded_industries
    s.location = location
    s.remote_preference = remote_preference
    s.additional_notes = additional_notes
    return s


def test_has_stored_params_returns_true_when_any_field_set():
    """The has_stored_params check is True if at least one field is not None."""
    old = _make_old_summary(excluded_industries="gambling")
    has_stored = any(
        getattr(old, f) is not None
        for f in ("excluded_industries", "location", "remote_preference", "additional_notes")
    )
    assert has_stored is True


def test_has_stored_params_returns_false_when_all_none():
    """The has_stored_params check is False if every field is None (legacy row)."""
    old = _make_old_summary()
    has_stored = any(
        getattr(old, f) is not None
        for f in ("excluded_industries", "location", "remote_preference", "additional_notes")
    )
    assert has_stored is False


def test_regenerate_clones_params_to_new_summary_and_enqueues():
    """
    When old summary has stored params, regenerate creates a new row with
    cloned params and calls the Celery task — without touching FSM.
    """
    from src.bot.modules.vacancy_summary.handlers import _enqueue_summary

    old = _make_old_summary(
        user_id=1,
        excluded_industries="gambling",
        location="Moscow",
        remote_preference="remote",
        additional_notes="notes",
    )

    new_summary = MagicMock()
    new_summary.id = 100
    new_summary.excluded_industries = old.excluded_industries
    new_summary.location = old.location
    new_summary.remote_preference = old.remote_preference
    new_summary.additional_notes = old.additional_notes

    with patch("src.worker.tasks.vacancy_summary.generate_vacancy_summary_task") as mock_task:
        mock_task.delay = MagicMock()
        _enqueue_summary(
            new_summary.id,
            1,
            new_summary.excluded_industries,
            new_summary.location,
            new_summary.remote_preference,
            new_summary.additional_notes,
            chat_id=123,
            message_id=456,
            locale="ru",
        )
        mock_task.delay.assert_called_once_with(
            100,
            1,
            "gambling",
            "Moscow",
            "remote",
            "notes",
            123,
            456,
            "ru",
            "",
        )


def test_enqueue_summary_passes_none_params():
    """_enqueue_summary passes None values unchanged to the task."""
    from src.bot.modules.vacancy_summary.handlers import _enqueue_summary

    with patch("src.worker.tasks.vacancy_summary.generate_vacancy_summary_task") as mock_task:
        mock_task.delay = MagicMock()
        _enqueue_summary(
            summary_id=1,
            user_id=2,
            excluded_industries=None,
            location=None,
            remote_preference=None,
            additional_notes=None,
            chat_id=10,
            message_id=20,
            locale="en",
        )
        mock_task.delay.assert_called_once_with(1, 2, None, None, None, None, 10, 20, "en", "")


# ── Bug fix: handle_regenerate wait_msg NameError ─────────────────────────────


def _make_summary(user_id: int = 1, summary_id: int = 10) -> MagicMock:
    s = MagicMock()
    s.id = summary_id
    s.user_id = user_id
    s.is_deleted = False
    s.excluded_industries = "gambling"
    s.location = "Moscow"
    s.remote_preference = "remote"
    s.additional_notes = "notes"
    return s


def _make_callback_for_regenerate(chat_id: int = 5, message_id: int = 99) -> AsyncMock:
    callback = AsyncMock()
    callback.message = AsyncMock()
    callback.message.chat = MagicMock()
    callback.message.chat.id = chat_id
    callback.message.message_id = message_id
    return callback


@pytest.mark.asyncio
async def test_handle_regenerate_falls_back_to_original_message_id_when_edit_raises():
    """When edit_text raises TelegramBadRequest, handler must NOT raise NameError.

    wait_msg must be initialised to None before the suppress block so that
    the subsequent ``wait_msg.message_id if wait_msg else ...`` expression
    safely falls back to callback.message.message_id.
    """
    from aiogram.exceptions import TelegramBadRequest

    from src.bot.modules.vacancy_summary.callbacks import VacancySummaryCallback
    from src.bot.modules.vacancy_summary.handlers import handle_regenerate
    from src.core.i18n import I18nContext

    old_summary = _make_summary(user_id=1, summary_id=10)
    new_summary = _make_summary(user_id=1, summary_id=20)

    callback = _make_callback_for_regenerate(chat_id=5, message_id=99)
    callback.message.edit_text.side_effect = TelegramBadRequest(
        method=MagicMock(), message="message is not modified"
    )

    callback_data = VacancySummaryCallback(action="regenerate", summary_id=10)
    user = MagicMock()
    user.id = 1
    user.language_code = "ru"
    state = AsyncMock()
    session = AsyncMock()
    i18n = I18nContext(locale="en")

    mock_repo = AsyncMock()
    mock_repo.get_by_id = AsyncMock(return_value=old_summary)
    mock_repo.soft_delete = AsyncMock()
    mock_repo.create = AsyncMock(return_value=new_summary)

    with (
        patch(
            "src.bot.modules.vacancy_summary.handlers.VacancySummaryRepository",
            return_value=mock_repo,
        ),
        patch("src.worker.tasks.vacancy_summary.generate_vacancy_summary_task") as mock_task,
    ):
        mock_task.delay = MagicMock()
        await handle_regenerate(callback, callback_data, user, state, session, i18n)

    mock_task.delay.assert_called_once()
    delay_args = mock_task.delay.call_args.args
    assert delay_args[6] == 5
    assert delay_args[7] == 99


@pytest.mark.asyncio
async def test_handle_regenerate_uses_wait_msg_id_when_edit_succeeds():
    """When edit_text succeeds, handle_regenerate passes the returned message_id."""
    from src.bot.modules.vacancy_summary.callbacks import VacancySummaryCallback
    from src.bot.modules.vacancy_summary.handlers import handle_regenerate
    from src.core.i18n import I18nContext

    old_summary = _make_summary(user_id=1, summary_id=10)
    new_summary = _make_summary(user_id=1, summary_id=20)

    wait_msg_mock = AsyncMock()
    wait_msg_mock.message_id = 77

    callback = _make_callback_for_regenerate(chat_id=5, message_id=99)
    callback.message.edit_text = AsyncMock(return_value=wait_msg_mock)

    callback_data = VacancySummaryCallback(action="regenerate", summary_id=10)
    user = MagicMock()
    user.id = 1
    user.language_code = "ru"
    state = AsyncMock()
    session = AsyncMock()
    i18n = I18nContext(locale="en")

    mock_repo = AsyncMock()
    mock_repo.get_by_id = AsyncMock(return_value=old_summary)
    mock_repo.soft_delete = AsyncMock()
    mock_repo.create = AsyncMock(return_value=new_summary)

    with (
        patch(
            "src.bot.modules.vacancy_summary.handlers.VacancySummaryRepository",
            return_value=mock_repo,
        ),
        patch("src.worker.tasks.vacancy_summary.generate_vacancy_summary_task") as mock_task,
    ):
        mock_task.delay = MagicMock()
        await handle_regenerate(callback, callback_data, user, state, session, i18n)

    mock_task.delay.assert_called_once()
    delay_args = mock_task.delay.call_args.args
    assert delay_args[7] == 77
