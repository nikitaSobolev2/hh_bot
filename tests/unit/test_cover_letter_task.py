"""Unit tests for cover letter generation task."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.worker.tasks.cover_letter import (
    COVER_LETTER_DISPLAY_MAX,
    _build_cover_letter_keyboard,
    _generate_cover_letter_async,
    _normalize_dashes,
    _sanitize_for_telegram,
    _strip_agent_wrapper,
    _truncate_for_display,
)


class TestSanitizeForTelegram:
    def test_removes_control_characters(self) -> None:
        text = "Hello\x00World\x01Test"
        assert _sanitize_for_telegram(text) == "HelloWorldTest"

    def test_preserves_newlines_and_tabs(self) -> None:
        text = "Line1\nLine2\tTab"
        assert _sanitize_for_telegram(text) == "Line1\nLine2\tTab"

    def test_returns_empty_for_empty_input(self) -> None:
        assert _sanitize_for_telegram("") == ""
        assert _sanitize_for_telegram("   ") == ""

    def test_truncates_to_4096(self) -> None:
        text = "a" * 5000
        assert len(_sanitize_for_telegram(text)) == 4096


class TestNormalizeDashes:
    def test_replaces_em_dash_with_hyphen(self) -> None:
        assert _normalize_dashes("Добрый день — Fullstack") == "Добрый день - Fullstack"

    def test_replaces_en_dash_with_hyphen(self) -> None:
        assert _normalize_dashes("2020–2023") == "2020-2023"

    def test_returns_empty_for_empty_input(self) -> None:
        assert _normalize_dashes("") == ""

    def test_preserves_regular_hyphen(self) -> None:
        assert _normalize_dashes("Node.js - Python") == "Node.js - Python"


class TestStripAgentWrapper:
    def test_returns_empty_for_empty_input(self) -> None:
        assert _strip_agent_wrapper("") == ""

    def test_returns_whitespace_for_whitespace_only_input(self) -> None:
        assert _strip_agent_wrapper("   ").strip() == ""

    def test_strips_leading_intro_phrase(self) -> None:
        text = "Вот сопроводительное письмо.\n\nДобрый день!"
        assert "Добрый день" in _strip_agent_wrapper(text)

    def test_preserves_mogu_podgotovit_in_call_to_action(self) -> None:
        """Phrases like «Могу подготовить» are legitimate in cover letters (call to action)."""
        text = (
            "Добрый день! Я заинтересован в вакансии.\n\n"
            "Могу подготовить презентацию моих проектов."
        )
        result = _strip_agent_wrapper(text)
        assert "Могу подготовить презентацию" in result


class TestTruncateForDisplay:
    def test_returns_full_text_when_within_limit(self) -> None:
        short = "Hello world"
        assert _truncate_for_display(short) == short

    def test_returns_full_text_when_exactly_at_limit(self) -> None:
        text = "x" * COVER_LETTER_DISPLAY_MAX
        assert _truncate_for_display(text) == text

    def test_truncates_with_ellipsis_when_over_limit(self) -> None:
        long_text = "a" * (COVER_LETTER_DISPLAY_MAX + 100)
        result = _truncate_for_display(long_text)
        assert len(result) == COVER_LETTER_DISPLAY_MAX - 10 + 4  # "\n..." = 4 chars
        assert result.endswith("\n...")


class TestBuildCoverLetterKeyboard:
    def test_returns_keyboard_with_fits_not_fit_show_later_regenerate_and_back(self) -> None:
        keyboard = _build_cover_letter_keyboard(session_id=1, vacancy_id=42, locale="ru")
        assert keyboard.inline_keyboard
        assert len(keyboard.inline_keyboard) == 3
        all_callback_datas = [
            btn.callback_data
            for row in keyboard.inline_keyboard
            for btn in row
        ]
        assert any("like" in d for d in all_callback_datas)
        assert any("dislike" in d for d in all_callback_datas)
        assert any("show_later" in d for d in all_callback_datas)
        assert any("regenerate_cover_letter" in d for d in all_callback_datas)
        assert any("back_to_vacancy" in d for d in all_callback_datas)


@pytest.mark.asyncio
async def test_cover_letter_task_disabled_returns_early() -> None:
    task = MagicMock()
    task.check_enabled = AsyncMock(return_value=False)

    session = AsyncMock()
    session_factory = AsyncMock()
    session_factory.return_value.__aenter__.return_value = session
    session_factory.return_value.__aexit__.return_value = None

    result = await _generate_cover_letter_async(
        task,
        session_factory,
        user_id=1,
        vacancy_id=10,
        chat_id=123,
        message_id=456,
        locale="ru",
        cover_letter_style="professional",
        session_id=0,
    )

    assert result == {"status": "disabled"}
    task.check_enabled.assert_called_once()


@pytest.mark.asyncio
async def test_cover_letter_task_circuit_open_returns_early() -> None:
    task = MagicMock()
    task.check_enabled = AsyncMock(return_value=True)
    cb = MagicMock()
    cb.is_call_allowed.return_value = False
    task.load_circuit_breaker = AsyncMock(return_value=cb)

    session = AsyncMock()
    session_factory = AsyncMock()
    session_factory.return_value.__aenter__.return_value = session
    session_factory.return_value.__aexit__.return_value = None

    result = await _generate_cover_letter_async(
        task,
        session_factory,
        user_id=1,
        vacancy_id=10,
        chat_id=123,
        message_id=456,
        locale="ru",
        cover_letter_style="professional",
        session_id=0,
    )

    assert result == {"status": "circuit_open"}


@pytest.mark.asyncio
async def test_cover_letter_task_vacancy_not_found_returns_early() -> None:
    task = MagicMock()
    task.check_enabled = AsyncMock(return_value=True)
    cb = MagicMock()
    cb.is_call_allowed.return_value = True
    task.load_circuit_breaker = AsyncMock(return_value=cb)

    session = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    session_factory = MagicMock(return_value=ctx)

    with (
        patch(
            "src.repositories.task.CeleryTaskRepository"
        ) as mock_task_repo_cls,
        patch(
            "src.repositories.work_experience.WorkExperienceRepository"
        ) as mock_we_repo_cls,
        patch(
            "src.repositories.autoparse.AutoparsedVacancyRepository"
        ) as mock_vac_repo_cls,
    ):
        mock_task_repo = AsyncMock()
        mock_task_repo.get_by_idempotency_key = AsyncMock(return_value=None)
        mock_task_repo_cls.return_value = mock_task_repo

        mock_we_repo = AsyncMock()
        mock_we_repo.get_active_by_user = AsyncMock(return_value=[])
        mock_we_repo_cls.return_value = mock_we_repo

        mock_vac_repo = AsyncMock()
        mock_vac_repo.get_by_id = AsyncMock(return_value=None)
        mock_vac_repo_cls.return_value = mock_vac_repo

        result = await _generate_cover_letter_async(
            task,
            session_factory,
            user_id=1,
            vacancy_id=999,
            chat_id=123,
            message_id=456,
            locale="ru",
            cover_letter_style="professional",
            session_id=0,
        )

    assert result == {"status": "vacancy_not_found"}


def _cover_letter_bot_mock() -> MagicMock:
    bot = MagicMock()
    bot.delete_message = AsyncMock()
    bot.session = MagicMock()
    bot.session.close = AsyncMock()
    return bot


@pytest.mark.asyncio
async def test_cover_letter_task_streaming_success_deletes_placeholder() -> None:
    task = MagicMock()
    task.check_enabled = AsyncMock(return_value=True)
    cb = MagicMock()
    cb.is_call_allowed.return_value = True
    task.load_circuit_breaker = AsyncMock(return_value=cb)
    task_bot = _cover_letter_bot_mock()
    task.create_bot = MagicMock(return_value=task_bot)
    task.notify_user = AsyncMock()
    task.mark_completed = AsyncMock()

    vacancy = MagicMock()
    vacancy.title = "Lead Python Developer"
    vacancy.description = "Python, FastAPI."
    vacancy.company_name = "Acme"

    session = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    session_factory = MagicMock(return_value=ctx)

    mock_user = MagicMock()
    mock_user.first_name = "Иван"
    mock_user.last_name = ""

    with (
        patch("src.repositories.task.CeleryTaskRepository") as mock_task_repo_cls,
        patch("src.repositories.work_experience.WorkExperienceRepository") as mock_we_repo_cls,
        patch("src.repositories.autoparse.AutoparsedVacancyRepository") as mock_vac_repo_cls,
        patch(
            "src.bot.modules.autoparse.services.get_user_autoparse_settings",
            new_callable=AsyncMock,
        ) as mock_settings,
        patch("src.repositories.user.UserRepository") as mock_user_repo_cls,
        patch(
            "src.services.ai.streaming.stream_to_telegram",
            new_callable=AsyncMock,
        ) as mock_stream,
        patch("src.services.ai.client.AIClient") as mock_ai_cls,
    ):
        mock_task_repo = AsyncMock()
        mock_task_repo.get_by_idempotency_key = AsyncMock(return_value=None)
        mock_task_repo_cls.return_value = mock_task_repo

        mock_we_repo = AsyncMock()
        mock_we_repo.get_active_by_user = AsyncMock(return_value=[])
        mock_we_repo_cls.return_value = mock_we_repo

        mock_vac_repo = AsyncMock()
        mock_vac_repo.get_by_id = AsyncMock(return_value=vacancy)
        mock_vac_repo_cls.return_value = mock_vac_repo

        mock_settings.return_value = {"user_name": "Иван", "about_me": ""}

        mock_user_repo = AsyncMock()
        mock_user_repo.get_by_id = AsyncMock(return_value=mock_user)
        mock_user_repo_cls.return_value = mock_user_repo

        mock_stream.return_value = "Иван - разработчик. Релевантен для вакансии."
        mock_ai_cls.return_value = MagicMock()

        result = await _generate_cover_letter_async(
            task,
            session_factory,
            user_id=1,
            vacancy_id=10,
            chat_id=123,
            message_id=456,
            locale="ru",
            cover_letter_style="professional",
            session_id=1,
        )

    assert result == {"status": "completed", "vacancy_id": 10, "locale": "ru"}
    mock_stream.assert_awaited_once()
    task.notify_user.assert_not_called()
    task_bot.delete_message.assert_awaited_once_with(chat_id=123, message_id=456)
    task.mark_completed.assert_awaited_once()
    call_kw = task.mark_completed.await_args.kwargs
    assert call_kw["result_data"]["generated_text"] == (
        "Иван - разработчик. Релевантен для вакансии."
    )
    cb.record_success.assert_called_once()
    task_bot.session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_cover_letter_task_fallback_when_stream_raises() -> None:
    task = MagicMock()
    task.check_enabled = AsyncMock(return_value=True)
    cb = MagicMock()
    cb.is_call_allowed.return_value = True
    task.load_circuit_breaker = AsyncMock(return_value=cb)
    task_bot = _cover_letter_bot_mock()
    task.create_bot = MagicMock(return_value=task_bot)
    task.notify_user = AsyncMock()
    task.mark_completed = AsyncMock()

    vacancy = MagicMock()
    vacancy.title = "Python Developer"
    vacancy.description = "Desc"
    vacancy.company_name = "Corp"

    session = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    session_factory = MagicMock(return_value=ctx)

    mock_user = MagicMock()
    mock_user.first_name = None
    mock_user.last_name = None

    ai_instance = MagicMock()
    ai_instance.generate_text = AsyncMock(return_value="Fallback письмо.")

    with (
        patch("src.repositories.task.CeleryTaskRepository") as mock_task_repo_cls,
        patch("src.repositories.work_experience.WorkExperienceRepository") as mock_we_repo_cls,
        patch("src.repositories.autoparse.AutoparsedVacancyRepository") as mock_vac_repo_cls,
        patch(
            "src.bot.modules.autoparse.services.get_user_autoparse_settings",
            new_callable=AsyncMock,
        ) as mock_settings,
        patch("src.repositories.user.UserRepository") as mock_user_repo_cls,
        patch(
            "src.services.ai.streaming.stream_to_telegram",
            new_callable=AsyncMock,
        ) as mock_stream,
        patch("src.services.ai.client.AIClient") as mock_ai_cls,
    ):
        mock_task_repo = AsyncMock()
        mock_task_repo.get_by_idempotency_key = AsyncMock(return_value=None)
        mock_task_repo_cls.return_value = mock_task_repo

        mock_we_repo = AsyncMock()
        mock_we_repo.get_active_by_user = AsyncMock(return_value=[])
        mock_we_repo_cls.return_value = mock_we_repo

        mock_vac_repo = AsyncMock()
        mock_vac_repo.get_by_id = AsyncMock(return_value=vacancy)
        mock_vac_repo_cls.return_value = mock_vac_repo

        mock_settings.return_value = {"user_name": "", "about_me": ""}

        mock_user_repo = AsyncMock()
        mock_user_repo.get_by_id = AsyncMock(return_value=mock_user)
        mock_user_repo_cls.return_value = mock_user_repo

        mock_stream.side_effect = RuntimeError("draft API unavailable")
        mock_ai_cls.return_value = ai_instance

        result = await _generate_cover_letter_async(
            task,
            session_factory,
            user_id=1,
            vacancy_id=10,
            chat_id=123,
            message_id=456,
            locale="ru",
            cover_letter_style="professional",
            session_id=0,
        )

    assert result == {"status": "completed", "vacancy_id": 10, "locale": "ru"}
    ai_instance.generate_text.assert_awaited_once()
    task.notify_user.assert_awaited_once()
    task_bot.delete_message.assert_not_called()
    stored = task.mark_completed.await_args.kwargs["result_data"]["generated_text"]
    assert stored == "Fallback письмо."
    assert cb.record_success.call_count == 1
    task_bot.session.close.assert_awaited_once()
