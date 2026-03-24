"""Unit tests for the interactive vacancy feed handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.modules.autoparse.callbacks import FeedCallback


def _make_callback(session_id: int, action: str, vacancy_id: int = 0):
    """Build a minimal CallbackQuery mock and matching callback_data for feed handler tests."""
    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.message = MagicMock()
    callback.message.edit_text = AsyncMock()

    callback_data = MagicMock()
    callback_data.session_id = session_id
    callback_data.action = action
    callback_data.vacancy_id = vacancy_id
    return callback, callback_data


def _make_i18n(locale: str = "ru") -> MagicMock:
    i18n = MagicMock()
    i18n.locale = locale
    i18n.get = MagicMock(side_effect=lambda key, **kwargs: key)
    return i18n


# ── handle_feed_start ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_feed_start_sends_first_vacancy_card(make_feed_session, make_vacancy):
    callback, callback_data = _make_callback(session_id=1, action="start")
    mock_session = AsyncMock()
    feed_session = make_feed_session(
        session_id=1, vacancy_ids=[10, 20], current_index=0, is_completed=False
    )
    vacancy = make_vacancy(vacancy_id=10, url="https://hh.ru/10")

    with (
        patch(
            "src.bot.modules.autoparse.feed_handlers.feed_services.get_feed_session",
            AsyncMock(return_value=feed_session),
        ),
        patch("src.bot.modules.autoparse.feed_handlers.AutoparsedVacancyRepository") as mock_repo,
    ):
        mock_repo_instance = AsyncMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=vacancy)
        mock_repo.return_value = mock_repo_instance

        from src.bot.modules.autoparse.feed_handlers import handle_feed_start

        await handle_feed_start(
            callback=callback,
            callback_data=callback_data,
            session=mock_session,
            user=MagicMock(),
            i18n=_make_i18n(),
        )

    callback.message.edit_text.assert_called_once()
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_handle_feed_start_alerts_when_session_not_found():
    callback, callback_data = _make_callback(session_id=999, action="start")
    mock_session = AsyncMock()

    with patch(
        "src.bot.modules.autoparse.feed_handlers.feed_services.get_feed_session",
        AsyncMock(return_value=None),
    ):
        from src.bot.modules.autoparse.feed_handlers import handle_feed_start

        await handle_feed_start(
            callback=callback,
            callback_data=callback_data,
            session=mock_session,
            user=MagicMock(),
            i18n=_make_i18n(),
        )

    callback.answer.assert_called_once()
    assert callback.answer.call_args.kwargs.get("show_alert") is True
    callback.message.edit_text.assert_not_called()


@pytest.mark.asyncio
async def test_handle_feed_start_alerts_when_session_completed(make_feed_session):
    callback, callback_data = _make_callback(session_id=1, action="start")
    mock_session = AsyncMock()
    feed_session = make_feed_session(is_completed=True)

    with patch(
        "src.bot.modules.autoparse.feed_handlers.feed_services.get_feed_session",
        AsyncMock(return_value=feed_session),
    ):
        from src.bot.modules.autoparse.feed_handlers import handle_feed_start

        await handle_feed_start(
            callback=callback,
            callback_data=callback_data,
            session=mock_session,
            user=MagicMock(),
            i18n=_make_i18n(),
        )

    callback.answer.assert_called_once()
    assert callback.answer.call_args.kwargs.get("show_alert") is True


# ── handle_feed_react ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_feed_react_like_advances_to_next_vacancy(make_feed_session, make_vacancy):
    callback, callback_data = _make_callback(session_id=1, action="like", vacancy_id=10)
    mock_session = AsyncMock()
    feed_session = make_feed_session(vacancy_ids=[10, 20], current_index=0, is_completed=False)
    next_vacancy = make_vacancy(vacancy_id=20, url="https://hh.ru/20")

    async def simulate_record_reaction(session, fs, vacancy_id, is_like):
        fs.current_index = 1

    with (
        patch(
            "src.bot.modules.autoparse.feed_handlers.feed_services.get_feed_session",
            AsyncMock(return_value=feed_session),
        ),
        patch(
            "src.bot.modules.autoparse.feed_handlers.feed_services.record_reaction",
            side_effect=simulate_record_reaction,
        ),
        patch("src.bot.modules.autoparse.feed_handlers.AutoparsedVacancyRepository") as mock_repo,
    ):
        mock_repo_instance = AsyncMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=next_vacancy)
        mock_repo.return_value = mock_repo_instance

        from src.bot.modules.autoparse.feed_handlers import handle_feed_react

        await handle_feed_react(
            callback=callback,
            callback_data=callback_data,
            session=mock_session,
            user=MagicMock(),
            i18n=_make_i18n(),
        )

    callback.message.edit_text.assert_called_once()
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_handle_feed_react_on_last_vacancy_shows_results(make_feed_session, make_vacancy):
    callback, callback_data = _make_callback(session_id=1, action="like", vacancy_id=10)
    mock_session = AsyncMock()
    feed_session = make_feed_session(
        vacancy_ids=[10],
        current_index=0,
        liked_ids=[],
        disliked_ids=[],
        is_completed=False,
    )

    async def simulate_record_reaction(session, fs, vacancy_id, is_like):
        fs.current_index = 1
        fs.liked_ids = [vacancy_id]

    with (
        patch(
            "src.bot.modules.autoparse.feed_handlers.feed_services.get_feed_session",
            AsyncMock(return_value=feed_session),
        ),
        patch(
            "src.bot.modules.autoparse.feed_handlers.feed_services.record_reaction",
            side_effect=simulate_record_reaction,
        ),
        patch(
            "src.bot.modules.autoparse.feed_handlers.feed_services.complete_feed_session",
            AsyncMock(return_value=None),
        ),
        patch("src.bot.modules.autoparse.feed_handlers.AutoparsedVacancyRepository") as mock_repo,
    ):
        mock_repo_instance = AsyncMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=make_vacancy(vacancy_id=10))
        mock_repo.return_value = mock_repo_instance

        from src.bot.modules.autoparse.feed_handlers import handle_feed_react

        await handle_feed_react(
            callback=callback,
            callback_data=callback_data,
            session=mock_session,
            user=MagicMock(),
            i18n=_make_i18n(),
        )

    callback.message.edit_text.assert_called_once()
    callback.answer.assert_called_once()


# ── handle_feed_stop ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_feed_stop_marks_session_completed(make_feed_session):
    callback, callback_data = _make_callback(session_id=1, action="stop")
    mock_session = AsyncMock()
    feed_session = make_feed_session(
        vacancy_ids=[10, 20],
        current_index=1,
        liked_ids=[10],
        disliked_ids=[],
        is_completed=False,
    )

    complete_mock = AsyncMock(return_value=None)

    with (
        patch(
            "src.bot.modules.autoparse.feed_handlers.feed_services.get_feed_session",
            AsyncMock(return_value=feed_session),
        ),
        patch(
            "src.bot.modules.autoparse.feed_handlers.feed_services.complete_feed_session",
            complete_mock,
        ),
        patch("src.bot.modules.autoparse.feed_handlers.AutoparsedVacancyRepository") as mock_repo,
    ):
        mock_repo_instance = AsyncMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=None)
        mock_repo.return_value = mock_repo_instance

        from src.bot.modules.autoparse.feed_handlers import handle_feed_stop

        await handle_feed_stop(
            callback=callback,
            callback_data=callback_data,
            session=mock_session,
            user=MagicMock(),
            i18n=_make_i18n(),
        )

    complete_mock.assert_called_once_with(mock_session, feed_session)
    callback.message.edit_text.assert_called_once()
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_handle_feed_stop_does_not_complete_already_completed_session(make_feed_session):
    callback, callback_data = _make_callback(session_id=1, action="stop")
    mock_session = AsyncMock()
    feed_session = make_feed_session(
        vacancy_ids=[10],
        current_index=1,
        liked_ids=[10],
        disliked_ids=[],
        is_completed=True,
    )

    complete_mock = AsyncMock(return_value=None)

    with (
        patch(
            "src.bot.modules.autoparse.feed_handlers.feed_services.get_feed_session",
            AsyncMock(return_value=feed_session),
        ),
        patch(
            "src.bot.modules.autoparse.feed_handlers.feed_services.complete_feed_session",
            complete_mock,
        ),
        patch("src.bot.modules.autoparse.feed_handlers.AutoparsedVacancyRepository") as mock_repo,
    ):
        mock_repo_instance = AsyncMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=None)
        mock_repo.return_value = mock_repo_instance

        from src.bot.modules.autoparse.feed_handlers import handle_feed_stop

        await handle_feed_stop(
            callback=callback,
            callback_data=callback_data,
            session=mock_session,
            user=MagicMock(),
            i18n=_make_i18n(),
        )

    complete_mock.assert_not_called()
    callback.message.edit_text.assert_called_once()


# ── handle_feed_back_to_vacancy ─────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_feed_back_to_vacancy_restores_vacancy_card(
    make_feed_session, make_vacancy
):
    callback, callback_data = _make_callback(
        session_id=1, action="back_to_vacancy", vacancy_id=10
    )
    mock_session = AsyncMock()
    feed_session = make_feed_session(
        session_id=1, vacancy_ids=[10, 20, 30], current_index=1, is_completed=False
    )
    vacancy = make_vacancy(vacancy_id=10, url="https://hh.ru/10")

    with (
        patch(
            "src.bot.modules.autoparse.feed_handlers.feed_services.get_feed_session",
            AsyncMock(return_value=feed_session),
        ),
        patch("src.bot.modules.autoparse.feed_handlers.AutoparsedVacancyRepository") as mock_repo,
    ):
        mock_repo_instance = AsyncMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=vacancy)
        mock_repo.return_value = mock_repo_instance

        from src.bot.modules.autoparse.feed_handlers import handle_feed_back_to_vacancy

        await handle_feed_back_to_vacancy(
            callback=callback,
            callback_data=callback_data,
            session=mock_session,
            user=MagicMock(),
            i18n=_make_i18n(),
        )

    callback.message.edit_text.assert_called_once()
    call_kwargs = callback.message.edit_text.call_args.kwargs
    assert "reply_markup" in call_kwargs
    assert call_kwargs.get("parse_mode") == "HTML"
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_handle_feed_back_to_vacancy_does_nothing_when_session_not_found():
    callback, callback_data = _make_callback(
        session_id=999, action="back_to_vacancy", vacancy_id=10
    )
    mock_session = AsyncMock()

    with patch(
        "src.bot.modules.autoparse.feed_handlers.feed_services.get_feed_session",
        AsyncMock(return_value=None),
    ):
        from src.bot.modules.autoparse.feed_handlers import handle_feed_back_to_vacancy

        await handle_feed_back_to_vacancy(
            callback=callback,
            callback_data=callback_data,
            session=mock_session,
            user=MagicMock(),
            i18n=_make_i18n(),
        )

    callback.answer.assert_called_once()
    callback.message.edit_text.assert_not_called()


@pytest.mark.asyncio
async def test_handle_feed_regenerate_cover_letter_deletes_task_and_reruns(
    make_feed_session, make_vacancy
):
    callback, callback_data = _make_callback(
        session_id=1, action="regenerate_cover_letter", vacancy_id=10
    )
    mock_session = AsyncMock()
    feed_session = make_feed_session(
        session_id=1, vacancy_ids=[10, 20], is_completed=False
    )
    vacancy = make_vacancy(vacancy_id=10, url="https://hh.ru/10")

    task_repo_delete = AsyncMock(return_value=True)
    run_celery_mock = AsyncMock()
    ap_settings = AsyncMock(return_value={"cover_letter_style": "professional"})

    with (
        patch(
            "src.bot.modules.autoparse.feed_handlers.feed_services.get_feed_session",
            AsyncMock(return_value=feed_session),
        ),
        patch(
            "src.bot.modules.autoparse.services.get_user_autoparse_settings",
            ap_settings,
        ),
        patch("src.bot.modules.autoparse.feed_handlers.AutoparsedVacancyRepository") as mock_repo,
        patch(
            "src.repositories.task.CeleryTaskRepository"
        ) as mock_task_repo_cls,
        patch(
            "src.core.celery_async.run_celery_task",
            run_celery_mock,
        ),
    ):
        mock_repo_instance = AsyncMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=vacancy)
        mock_repo.return_value = mock_repo_instance

        mock_task_repo = AsyncMock()
        mock_task_repo.delete_by_idempotency_key = task_repo_delete
        mock_task_repo_cls.return_value = mock_task_repo

        from src.bot.modules.autoparse.feed_handlers import (
            handle_feed_regenerate_cover_letter,
        )

        await handle_feed_regenerate_cover_letter(
            callback=callback,
            callback_data=callback_data,
            session=mock_session,
            user=MagicMock(id=1, language_code="ru"),
            i18n=_make_i18n(),
        )

    task_repo_delete.assert_called_once_with("cover_letter:1:autoparse:10")
    run_celery_mock.assert_called_once()
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_handle_feed_back_to_vacancy_does_nothing_when_vacancy_not_found(
    make_feed_session,
):
    callback, callback_data = _make_callback(
        session_id=1, action="back_to_vacancy", vacancy_id=999
    )
    mock_session = AsyncMock()
    feed_session = make_feed_session(
        session_id=1, vacancy_ids=[10, 20], is_completed=False
    )

    with (
        patch(
            "src.bot.modules.autoparse.feed_handlers.feed_services.get_feed_session",
            AsyncMock(return_value=feed_session),
        ),
        patch("src.bot.modules.autoparse.feed_handlers.AutoparsedVacancyRepository") as mock_repo,
    ):
        mock_repo_instance = AsyncMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=None)
        mock_repo.return_value = mock_repo_instance

        from src.bot.modules.autoparse.feed_handlers import handle_feed_back_to_vacancy

        await handle_feed_back_to_vacancy(
            callback=callback,
            callback_data=callback_data,
            session=mock_session,
            user=MagicMock(),
            i18n=_make_i18n(),
        )

    callback.answer.assert_called_once()
    callback.message.edit_text.assert_not_called()


def test_feed_callback_pack_roundtrip_respond_letter_actions():
    for action in ("respond_ai_cover", "respond_letter_generate", "respond_letter_skip"):
        cb = FeedCallback(action=action, session_id=1, vacancy_id=42)
        packed = cb.pack()
        parsed = FeedCallback.unpack(packed)
        assert parsed.action == action
        assert parsed.session_id == 1
        assert parsed.vacancy_id == 42
