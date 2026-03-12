"""Unit tests for vacancy feed toggle (F1) and button rename (F2)."""

from unittest.mock import MagicMock


def _make_vacancy(
    ai_summary: str | None = None,
    description: str | None = None,
) -> MagicMock:
    v = MagicMock()
    v.title = "Python Developer"
    v.url = "https://hh.ru/vacancy/1"
    v.company_name = "ACME Corp"
    v.salary = None
    v.work_experience = None
    v.employment_type = None
    v.work_schedule = None
    v.working_hours = None
    v.work_formats = None
    v.raw_skills = []
    v.compatibility_score = None
    v.ai_summary = ai_summary
    v.description = description
    return v


def test_build_vacancy_card_summary_mode_shows_ai_summary():
    """In summary mode, ai_summary is shown if available."""
    from src.bot.modules.autoparse.feed_services import build_vacancy_card

    vacancy = _make_vacancy(ai_summary="AI generated summary", description="Full description")
    card = build_vacancy_card(vacancy, 0, 10, mode="summary")

    assert "AI generated summary" in card
    assert "Full description" not in card


def test_build_vacancy_card_description_mode_shows_full_description():
    """In description mode, full description is shown instead of summary."""
    from src.bot.modules.autoparse.feed_services import build_vacancy_card

    vacancy = _make_vacancy(ai_summary="AI generated summary", description="Full description")
    card = build_vacancy_card(vacancy, 0, 10, mode="description")

    assert "Full description" in card
    assert "AI generated summary" not in card


def test_build_vacancy_card_summary_mode_falls_back_to_truncated_description():
    """In summary mode with no ai_summary, truncated description is shown."""
    from src.bot.modules.autoparse.feed_services import build_vacancy_card

    long_description = "x" * 1000
    vacancy = _make_vacancy(ai_summary=None, description=long_description)
    card = build_vacancy_card(vacancy, 0, 10, mode="summary")

    assert "x" in card
    assert "AI" not in card


def test_feed_vacancy_keyboard_has_toggle_button_in_summary_mode():
    """In summary mode, keyboard has 'show description' toggle button."""
    from unittest.mock import MagicMock

    from src.bot.modules.autoparse.feed_handlers import feed_vacancy_keyboard

    mock_i18n = MagicMock()
    mock_i18n.get.side_effect = lambda key: key

    kb = feed_vacancy_keyboard(
        session_id=1,
        vacancy_id=99,
        vacancy_url="https://hh.ru/vacancy/1",
        i18n=mock_i18n,
        mode="summary",
    )

    all_texts = [btn.text for row in kb.inline_keyboard for btn in row]
    callback_datas = [
        btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data
    ]

    assert "feed-btn-show-description" in all_texts
    assert any("toggle_view" in cd for cd in callback_datas)


def test_feed_vacancy_keyboard_uses_fits_me_not_fit_buttons():
    """Feed keyboard uses fits_me and not_fit button keys (F2)."""
    from unittest.mock import MagicMock

    from src.bot.modules.autoparse.feed_handlers import feed_vacancy_keyboard

    mock_i18n = MagicMock()
    mock_i18n.get.side_effect = lambda key: key

    kb = feed_vacancy_keyboard(
        session_id=1,
        vacancy_id=99,
        vacancy_url="https://hh.ru/vacancy/1",
        i18n=mock_i18n,
    )

    all_texts = [btn.text for row in kb.inline_keyboard for btn in row]

    assert "feed-btn-fits-me" in all_texts
    assert "feed-btn-not-fit" in all_texts
    assert "feed-btn-like" not in all_texts
    assert "feed-btn-dislike" not in all_texts
