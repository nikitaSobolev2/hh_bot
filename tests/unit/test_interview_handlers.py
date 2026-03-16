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
    assert "Prepare" in flat[0] or "Подготовь" in flat[0]
    assert "Results" in flat[1] or "Результаты" in flat[1]


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
