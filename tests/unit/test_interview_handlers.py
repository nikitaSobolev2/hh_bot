"""Unit tests for interview handlers and keyboards.

Covers: source choice keyboard (no plain option), interview detail keyboard
(Prepare me, Results, Delete, Back), and _save_and_show_interview.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.i18n import I18nContext


def _make_i18n(locale: str = "en") -> I18nContext:
    return I18nContext(locale=locale)


# ── source_choice_keyboard ────────────────────────────────────────────────────


def test_source_choice_keyboard_has_hh_and_manual_only():
    """Source choice has HH and Manual options, no plain."""
    from src.bot.modules.interviews.keyboards import source_choice_keyboard

    kb = source_choice_keyboard(_make_i18n())
    buttons_text = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("HH" in t or "hh" in t.lower() for t in buttons_text)
    assert any("manual" in t.lower() or "вручную" in t.lower() for t in buttons_text)
    assert not any("Just save" in t or "Просто сохранить" in t for t in buttons_text)


# ── interview_detail_keyboard ────────────────────────────────────────────────


def test_interview_detail_keyboard_has_prepare_me_results_delete_back():
    """Interview detail has Prepare me, Results (when no Q&A), Delete, Back."""
    from src.bot.modules.interviews.keyboards import interview_detail_keyboard

    kb = interview_detail_keyboard(
        interview_id=1,
        improvements=[],
        i18n=_make_i18n(),
        has_questions=False,
    )
    buttons_text = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("Prepare" in t or "Подготовь" in t for t in buttons_text)
    assert any("Results" in t or "Результаты" in t for t in buttons_text)
    assert any("Delete" in t or "Удалить" in t for t in buttons_text)
    assert any("Back" in t or "Назад" in t for t in buttons_text)


def test_interview_detail_keyboard_prepare_me_before_results_when_no_questions():
    """Prepare me button appears before Results when has_questions=False."""
    from src.bot.modules.interviews.keyboards import interview_detail_keyboard

    kb = interview_detail_keyboard(
        interview_id=1,
        improvements=[],
        i18n=_make_i18n(),
        has_questions=False,
    )
    flat = [btn.text for row in kb.inline_keyboard for btn in row]
    prepare_idx = next(
        i for i, t in enumerate(flat) if "Prepare" in t or "Подготовь" in t
    )
    results_idx = next(
        i for i, t in enumerate(flat) if "Results" in t or "Результаты" in t
    )
    assert prepare_idx < results_idx


# ── _save_and_show_interview ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_and_show_interview_creates_and_edits_message():
    """_save_and_show_interview creates interview and edits message with detail view."""
    from src.bot.modules.interviews.handlers import _save_and_show_interview

    message = AsyncMock()
    message.edit_text = AsyncMock(return_value=MagicMock())

    user = MagicMock()
    user.id = 42

    session = AsyncMock()
    i18n = _make_i18n()

    data = {
        "vacancy_title": "Python Dev",
        "vacancy_description": "Desc",
        "company_name": "Acme",
        "experience_level": "3-6",
        "hh_vacancy_url": None,
    }

    mock_interview = MagicMock()
    mock_interview.id = 99
    mock_interview.vacancy_title = "Python Dev"
    mock_interview.company_name = "Acme"
    mock_interview.experience_level = "3-6"
    mock_interview.hh_vacancy_url = None

    with patch(
        "src.bot.modules.interviews.handlers.interview_service"
    ) as mock_svc:
        mock_svc.create_interview = AsyncMock(return_value=mock_interview)
        mock_svc.format_vacancy_header = MagicMock(
            return_value="<b>🏢 Python Dev</b>"
        )

        await _save_and_show_interview(message, user, session, i18n, data)

    mock_svc.create_interview.assert_called_once()
    call_kw = mock_svc.create_interview.call_args.kwargs
    assert call_kw["user_id"] == 42
    assert call_kw["vacancy_title"] == "Python Dev"

    message.edit_text.assert_called_once()
    edit_args = message.edit_text.call_args
    assert "Python Dev" in edit_args[0][0]
    assert edit_args[1]["reply_markup"] is not None


# ── handle_prep_step_deep (multi-message) ────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_prep_step_deep_single_chunk_edits_with_keyboard():
    """Single chunk: edit_text with parse_mode Markdown and keyboard."""
    from src.bot.modules.interviews.callbacks import InterviewCallback
    from src.bot.modules.interviews.handlers import handle_prep_step_deep

    callback = AsyncMock()
    callback.message = AsyncMock()
    callback.message.bot = MagicMock()
    callback.message.chat = MagicMock()
    callback.message.chat.id = 123
    callback.message.document = None
    callback.message.edit_text = AsyncMock(return_value=MagicMock())

    callback_data = InterviewCallback(
        action="prep_step_deep",
        interview_id=1,
        prep_step_id=10,
    )

    step = MagicMock()
    step.id = 10
    step.title = "Symfony"
    step.deep_summary = "Short summary"
    step.test = None

    session = AsyncMock()
    i18n = _make_i18n()

    with patch(
        "src.repositories.interview.InterviewPreparationRepository"
    ) as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.get_step_by_id = AsyncMock(return_value=step)
        mock_repo_cls.return_value = mock_repo

        await handle_prep_step_deep(
            callback, callback_data, MagicMock(), session, i18n
        )

    callback.message.edit_text.assert_called_once()
    edit_kw = callback.message.edit_text.call_args.kwargs
    assert edit_kw.get("parse_mode") == "Markdown"
    assert edit_kw.get("reply_markup") is not None
    assert "Symfony" in callback.message.edit_text.call_args[0][0]
    callback.message.bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_handle_prep_step_deep_multiple_chunks_sends_last_with_keyboard():
    """Multiple chunks: edit first, send rest; last has keyboard."""
    from src.bot.modules.interviews.callbacks import InterviewCallback
    from src.bot.modules.interviews.handlers import handle_prep_step_deep

    callback = AsyncMock()
    callback.message = AsyncMock()
    callback.message.bot = AsyncMock()
    callback.message.bot.send_message = AsyncMock(return_value=MagicMock())
    callback.message.chat = MagicMock()
    callback.message.chat.id = 123
    callback.message.document = None
    callback.message.edit_text = AsyncMock(return_value=MagicMock())

    callback_data = InterviewCallback(
        action="prep_step_deep",
        interview_id=1,
        prep_step_id=10,
    )

    step = MagicMock()
    step.id = 10
    step.title = "Symfony"
    step.deep_summary = ("A" * 500 + "\n\n") * 5 + ("B" * 500 + "\n\n") * 5
    step.test = None

    session = AsyncMock()
    i18n = _make_i18n()

    with patch(
        "src.repositories.interview.InterviewPreparationRepository"
    ) as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.get_step_by_id = AsyncMock(return_value=step)
        mock_repo_cls.return_value = mock_repo

        await handle_prep_step_deep(
            callback, callback_data, MagicMock(), session, i18n
        )

    callback.message.edit_text.assert_called_once()
    edit_kw = callback.message.edit_text.call_args.kwargs
    assert edit_kw.get("parse_mode") == "Markdown"
    assert "reply_markup" not in edit_kw or edit_kw.get("reply_markup") is None

    send_calls = callback.message.bot.send_message.call_args_list
    assert len(send_calls) >= 1
    last_send_kw = send_calls[-1].kwargs
    assert last_send_kw.get("reply_markup") is not None
    assert last_send_kw.get("parse_mode") == "Markdown"


@pytest.mark.asyncio
async def test_handle_prep_step_deep_from_document_deletes_and_sends_summary():
    """When back is clicked on document message, delete doc and send summary."""
    from src.bot.modules.interviews.callbacks import InterviewCallback
    from src.bot.modules.interviews.handlers import handle_prep_step_deep

    callback = AsyncMock()
    callback.message = AsyncMock()
    callback.message.bot = AsyncMock()
    callback.message.bot.send_message = AsyncMock(return_value=MagicMock())
    callback.message.chat = MagicMock()
    callback.message.chat.id = 123
    callback.message.document = MagicMock()
    callback.message.delete = AsyncMock(return_value=True)

    callback_data = InterviewCallback(
        action="prep_step_deep",
        interview_id=1,
        prep_step_id=10,
    )

    step = MagicMock()
    step.id = 10
    step.title = "Symfony"
    step.deep_summary = "Short summary"
    step.test = None

    session = AsyncMock()
    i18n = _make_i18n()

    with patch(
        "src.repositories.interview.InterviewPreparationRepository"
    ) as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.get_step_by_id = AsyncMock(return_value=step)
        mock_repo_cls.return_value = mock_repo

        await handle_prep_step_deep(
            callback, callback_data, MagicMock(), session, i18n
        )

    callback.message.delete.assert_called_once()
    callback.message.bot.send_message.assert_called_once()
    send_args = callback.message.bot.send_message.call_args
    assert send_args[0][0] == 123
    text = send_args[0][1] if len(send_args[0]) > 1 else ""
    assert "Symfony" in text
    assert send_args.kwargs.get("reply_markup") is not None


# ── handle_prep_download ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_prep_download_edits_to_download_options():
    """prep_download edits message to show download options keyboard."""
    from src.bot.modules.interviews.callbacks import InterviewCallback
    from src.bot.modules.interviews.handlers import handle_prep_download

    callback = AsyncMock()
    callback.message = AsyncMock()
    callback.message.edit_text = AsyncMock(return_value=MagicMock())

    callback_data = InterviewCallback(
        action="prep_download",
        interview_id=1,
        prep_step_id=10,
    )

    i18n = _make_i18n()

    await handle_prep_download(callback, callback_data, i18n)

    callback.message.edit_text.assert_called_once()
    edit_args = callback.message.edit_text.call_args
    assert "download" in edit_args[0][0].lower() or "скачать" in edit_args[0][0].lower()
    assert edit_args[1]["reply_markup"] is not None


# ── handle_prep_download_md ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_prep_download_md_sends_md_file_when_deep_summary_exists():
    """prep_download_md sends .md document when step has deep_summary."""
    from src.bot.modules.interviews.callbacks import InterviewCallback
    from src.bot.modules.interviews.handlers import handle_prep_download_md

    callback = AsyncMock()
    callback.message = AsyncMock()
    callback.message.chat = MagicMock()
    callback.message.chat.id = 123
    callback.message.bot = AsyncMock()
    callback.message.bot.send_document = AsyncMock(return_value=MagicMock())

    callback_data = InterviewCallback(
        action="prep_download_md",
        interview_id=1,
        prep_step_id=10,
    )

    step = MagicMock()
    step.id = 10
    step.title = "Python Basics"
    step.deep_summary = "Content here"

    session = AsyncMock()
    i18n = _make_i18n()

    with patch(
        "src.repositories.interview.InterviewPreparationRepository"
    ) as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.get_step_by_id = AsyncMock(return_value=step)
        mock_repo_cls.return_value = mock_repo

        await handle_prep_download_md(
            callback, callback_data, session, i18n
        )

    callback.message.bot.send_document.assert_called_once()
    send_args = callback.message.bot.send_document.call_args
    assert send_args[0][0] == 123
    assert send_args[1].get("caption") is not None


@pytest.mark.asyncio
async def test_handle_prep_download_md_answers_alert_when_no_deep_summary():
    """prep_download_md shows alert when step has no deep_summary."""
    from src.bot.modules.interviews.callbacks import InterviewCallback
    from src.bot.modules.interviews.handlers import handle_prep_download_md

    callback = AsyncMock()
    callback.answer = AsyncMock()

    callback_data = InterviewCallback(
        action="prep_download_md",
        interview_id=1,
        prep_step_id=10,
    )

    step = MagicMock()
    step.deep_summary = None

    session = AsyncMock()
    i18n = _make_i18n()

    with patch(
        "src.repositories.interview.InterviewPreparationRepository"
    ) as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.get_step_by_id = AsyncMock(return_value=step)
        mock_repo_cls.return_value = mock_repo

        await handle_prep_download_md(
            callback, callback_data, session, i18n
        )

    callback.answer.assert_called_once_with(
        i18n.get("prep-deep-not-ready"), show_alert=True
    )


# ── handle_prep_regenerate_deep ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_prep_regenerate_deep_clears_and_dispatches_task():
    """prep_regenerate_deep clears deep_summary and dispatches generate_deep_summary_task."""
    from src.bot.modules.interviews.callbacks import InterviewCallback
    from src.bot.modules.interviews.handlers import handle_prep_regenerate_deep

    callback = AsyncMock()
    callback.message = AsyncMock()
    callback.message.chat = MagicMock()
    callback.message.chat.id = 123
    callback.message.edit_text = AsyncMock(return_value=MagicMock())

    callback_data = InterviewCallback(
        action="prep_regenerate_deep",
        interview_id=1,
        prep_step_id=10,
    )

    user = MagicMock()
    user.language_code = "en"

    session = AsyncMock()
    session.commit = AsyncMock()
    i18n = _make_i18n()

    with patch(
        "src.repositories.interview.InterviewPreparationRepository"
    ) as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.update_step_deep_summary = AsyncMock()
        mock_repo_cls.return_value = mock_repo

        with patch(
            "src.core.celery_async.run_celery_task",
            new_callable=AsyncMock,
        ) as mock_run:
            await handle_prep_regenerate_deep(
                callback, callback_data, user, session, i18n
            )

    mock_repo.update_step_deep_summary.assert_called_once_with(10, None)
    session.commit.assert_called_once()
    mock_run.assert_called_once()
    call_args = mock_run.call_args
    assert call_args[0][1] == 10  # step_id
    assert call_args[0][2] == 1  # interview_id
    assert call_args[0][3] == 123  # chat_id


# ── handle_prep_regenerate_plan ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_prep_regenerate_plan_deletes_steps_and_dispatches_task():
    """prep_regenerate_plan deletes steps, clears idempotency, dispatches task."""
    from src.bot.modules.interviews.callbacks import InterviewCallback
    from src.bot.modules.interviews.handlers import handle_prep_regenerate_plan

    callback = AsyncMock()
    callback.message = AsyncMock()
    callback.message.chat = MagicMock()
    callback.message.chat.id = 123
    callback.message.edit_text = AsyncMock(return_value=MagicMock())

    callback_data = InterviewCallback(
        action="prep_regenerate_plan",
        interview_id=1,
    )

    user = MagicMock()
    user.language_code = "en"

    session = AsyncMock()
    session.commit = AsyncMock()
    i18n = _make_i18n()

    with patch(
        "src.repositories.interview.InterviewPreparationRepository"
    ) as mock_prep_repo_cls:
        mock_prep_repo = MagicMock()
        mock_prep_repo.delete_steps_for_interview = AsyncMock()
        mock_prep_repo_cls.return_value = mock_prep_repo

        with patch(
            "src.repositories.task.CeleryTaskRepository"
        ) as mock_task_repo_cls:
            mock_task_repo = MagicMock()
            mock_task_repo.delete_by_idempotency_key = AsyncMock()
            mock_task_repo_cls.return_value = mock_task_repo

            with patch(
                "src.core.celery_async.run_celery_task",
                new_callable=AsyncMock,
            ) as mock_run:
                await handle_prep_regenerate_plan(
                    callback, callback_data, user, session, i18n
                )

    mock_prep_repo.delete_steps_for_interview.assert_called_once_with(1)
    mock_task_repo.delete_by_idempotency_key.assert_called_once_with(
        "interview_prep:1"
    )
    session.commit.assert_called_once()
    mock_run.assert_called_once()


# ── handle_company_review ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_company_review_dispatches_task():
    """handle_company_review loads interview, edits to generating, dispatches task."""
    from src.bot.modules.interviews.callbacks import InterviewCallback
    from src.bot.modules.interviews.handlers import handle_company_review

    callback = AsyncMock()
    callback.message = AsyncMock()
    callback.message.chat = MagicMock()
    callback.message.chat.id = 123
    callback.message.message_id = 456
    callback.message.edit_text = AsyncMock(return_value=MagicMock())
    callback.answer = AsyncMock()

    callback_data = InterviewCallback(action="company_review", interview_id=1)

    mock_interview = MagicMock()
    mock_interview.id = 1
    mock_interview.is_deleted = False

    session = AsyncMock()
    i18n = _make_i18n()
    user = MagicMock()
    user.language_code = "en"

    with (
        patch(
            "src.repositories.interview.InterviewRepository"
        ) as mock_repo_cls,
        patch(
            "src.core.celery_async.run_celery_task",
            new_callable=AsyncMock,
        ) as mock_run,
    ):
        mock_repo = MagicMock()
        mock_repo.get_with_relations = AsyncMock(return_value=mock_interview)
        mock_repo_cls.return_value = mock_repo

        await handle_company_review(
            callback, callback_data, user, session, i18n
        )

    callback.message.edit_text.assert_called_once()
    mock_run.assert_called_once()
    call_args = mock_run.call_args[0]
    assert call_args[1] == 1  # interview_id
    assert call_args[2] == 123  # chat_id
    assert call_args[4] == "en"  # locale
    callback.answer.assert_called_once()


# ── handle_questions_to_ask ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_questions_to_ask_dispatches_task():
    """handle_questions_to_ask loads interview, edits to generating, dispatches task."""
    from src.bot.modules.interviews.callbacks import InterviewCallback
    from src.bot.modules.interviews.handlers import handle_questions_to_ask

    callback = AsyncMock()
    callback.message = AsyncMock()
    callback.message.chat = MagicMock()
    callback.message.chat.id = 123
    callback.message.message_id = 456
    callback.message.edit_text = AsyncMock(return_value=MagicMock())
    callback.answer = AsyncMock()

    callback_data = InterviewCallback(action="questions_to_ask", interview_id=1)

    mock_interview = MagicMock()
    mock_interview.id = 1
    mock_interview.is_deleted = False

    session = AsyncMock()
    i18n = _make_i18n()
    user = MagicMock()
    user.language_code = "en"

    with (
        patch(
            "src.repositories.interview.InterviewRepository"
        ) as mock_repo_cls,
        patch(
            "src.core.celery_async.run_celery_task",
            new_callable=AsyncMock,
        ) as mock_run,
    ):
        mock_repo = MagicMock()
        mock_repo.get_with_relations = AsyncMock(return_value=mock_interview)
        mock_repo_cls.return_value = mock_repo

        await handle_questions_to_ask(
            callback, callback_data, user, session, i18n
        )

    callback.message.edit_text.assert_called_once()
    mock_run.assert_called_once()
    call_args = mock_run.call_args[0]
    assert call_args[1] == 1  # interview_id
    assert call_args[2] == 123  # chat_id
    assert call_args[4] == "en"  # locale
    callback.answer.assert_called_once()
