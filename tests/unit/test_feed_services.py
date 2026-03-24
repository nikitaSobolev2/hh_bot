"""Unit tests for the interactive vacancy feed services."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.modules.autoparse.feed_services import (
    advance_feed_index,
    build_results_message,
    build_stats_message,
    build_vacancy_card,
    complete_feed_session,
    compute_feed_results,
    create_feed_session,
    format_ui_apply_result_line,
    get_feed_session,
    merge_liked_for_respond,
    move_vacancy_to_end,
    record_reaction,
    remove_vacancy_from_liked_ids,
)

# ── Pure function tests ─────────────────────────────────────────────


def test_merge_liked_for_respond_appends_and_removes_from_disliked():
    liked, disliked = merge_liked_for_respond([1, 2], [5, 3], 3)
    assert liked == [1, 2, 3]
    assert disliked == [5]


def test_merge_liked_for_respond_idempotent_when_already_liked():
    liked, disliked = merge_liked_for_respond([1, 3], [5], 3)
    assert liked == [1, 3]
    assert disliked == [5]


def test_remove_vacancy_from_liked_ids_filters():
    assert remove_vacancy_from_liked_ids([1, 2, 3], 2) == [1, 3]
    assert remove_vacancy_from_liked_ids([], 1) == []


def test_compute_feed_results_returns_correct_counts(make_feed_session, make_vacancy):
    feed_session = make_feed_session(
        vacancy_ids=[1, 2, 3, 4],
        current_index=3,
        liked_ids=[1, 3],
        disliked_ids=[2],
    )
    vacancy_1 = make_vacancy(vacancy_id=1, compatibility_score=80.0)
    vacancy_3 = make_vacancy(vacancy_id=3, compatibility_score=60.0)
    vacancies_by_id = {1: vacancy_1, 3: vacancy_3}

    results = compute_feed_results(feed_session, vacancies_by_id)

    assert results["seen"] == 3
    assert results["total"] == 4
    assert results["liked"] == 2
    assert results["disliked"] == 1


def test_compute_feed_results_calculates_avg_compat_of_liked(make_feed_session, make_vacancy):
    feed_session = make_feed_session(
        vacancy_ids=[1, 2],
        current_index=2,
        liked_ids=[1, 2],
        disliked_ids=[],
    )
    v1 = make_vacancy(vacancy_id=1, compatibility_score=80.0)
    v2 = make_vacancy(vacancy_id=2, compatibility_score=60.0)
    vacancies_by_id = {1: v1, 2: v2}

    results = compute_feed_results(feed_session, vacancies_by_id)

    assert results["avg_compat_liked"] == pytest.approx(70.0)


def test_compute_feed_results_no_liked_returns_none_avg(make_feed_session):
    feed_session = make_feed_session(
        vacancy_ids=[1, 2],
        current_index=2,
        liked_ids=[],
        disliked_ids=[1, 2],
    )
    results = compute_feed_results(feed_session, {})

    assert results["avg_compat_liked"] is None


def test_compute_feed_results_ignores_vacancies_without_compat_score(
    make_feed_session, make_vacancy
):
    feed_session = make_feed_session(
        vacancy_ids=[1, 2],
        current_index=2,
        liked_ids=[1, 2],
        disliked_ids=[],
    )
    v1 = make_vacancy(vacancy_id=1, compatibility_score=90.0)
    v2 = make_vacancy(vacancy_id=2, compatibility_score=None)
    vacancies_by_id = {1: v1, 2: v2}

    results = compute_feed_results(feed_session, vacancies_by_id)

    assert results["avg_compat_liked"] == pytest.approx(90.0)


def test_build_stats_message_includes_title_and_count():
    text = build_stats_message("Frontend Developer", 5, avg_compat=None)

    assert "Frontend Developer" in text
    assert "5" in text


def test_build_stats_message_includes_avg_compat_when_present():
    text = build_stats_message("Backend Dev", 10, avg_compat=75.0)

    assert "75" in text


def test_build_stats_message_omits_avg_compat_line_when_none():
    text = build_stats_message("Backend Dev", 10, avg_compat=None)

    assert "feed-stats-avg-compat" not in text


def test_build_vacancy_card_shows_progress(make_vacancy):
    vacancy = make_vacancy(vacancy_id=1)

    card = build_vacancy_card(vacancy, index=2, total=10)

    assert "3" in card
    assert "10" in card


def test_build_vacancy_card_includes_title_and_company(make_vacancy):
    vacancy = make_vacancy(
        title="Python Dev",
        url="https://hh.ru/1",
        company_name="TechCorp",
    )

    card = build_vacancy_card(vacancy, index=0, total=5)

    assert "Python Dev" in card
    assert "TechCorp" in card


def test_build_vacancy_card_includes_compatibility_score(make_vacancy):
    vacancy = make_vacancy(compatibility_score=85.0)

    card = build_vacancy_card(vacancy, index=0, total=1)

    assert "85" in card


def test_build_vacancy_card_skips_missing_optional_fields(make_vacancy):
    vacancy = make_vacancy(
        salary=None,
        work_experience=None,
        employment_type=None,
        company_name=None,
    )

    card = build_vacancy_card(vacancy, index=0, total=1)

    assert card  # should not raise and should have content


def test_build_vacancy_card_escapes_html_special_chars_in_description(make_vacancy):
    vacancy = make_vacancy(description="R&D team, salary > 100k, <senior> role")

    card = build_vacancy_card(vacancy, index=0, total=1)

    assert "&amp;" in card
    assert "&gt;" in card
    assert "&lt;" in card
    assert "R&D" not in card


def test_build_vacancy_card_escapes_html_special_chars_in_title(make_vacancy):
    vacancy = make_vacancy(title="Frontend & Backend Dev")

    card = build_vacancy_card(vacancy, index=0, total=1)

    assert "Frontend &amp; Backend Dev" in card
    assert "Frontend & Backend Dev" not in card


def test_build_vacancy_card_escapes_html_special_chars_in_company_name(make_vacancy):
    vacancy = make_vacancy(company_name="R&D Labs <Corp>")

    card = build_vacancy_card(vacancy, index=0, total=1)

    assert "R&amp;D Labs &lt;Corp&gt;" in card


def test_build_vacancy_card_shows_salary_with_currency_marker(make_vacancy):
    vacancy = make_vacancy(salary="200 000 ₽")

    card = build_vacancy_card(vacancy, index=0, total=1)

    assert "200 000 ₽" in card


def test_build_vacancy_card_skips_salary_without_currency_marker(make_vacancy):
    vacancy = make_vacancy(salary="4.4")

    card = build_vacancy_card(vacancy, index=0, total=1)

    assert "💰" not in card


def test_build_vacancy_card_skips_salary_when_only_rating_digits(make_vacancy):
    vacancy = make_vacancy(salary="4.2 из 5")

    card = build_vacancy_card(vacancy, index=0, total=1)

    assert "💰" not in card


def test_build_vacancy_card_cleans_malformed_salary(make_vacancy):
    vacancy = make_vacancy(salary="от4 000$за месяц,до вычета налогов")

    card = build_vacancy_card(vacancy, index=0, total=1)

    assert "от 4 000 $ за месяц" in card


def test_build_vacancy_card_shows_ai_summary_when_present(make_vacancy):
    vacancy = make_vacancy(
        description="Full raw description",
        ai_summary="Short AI-generated summary with pros and cons",
    )

    card = build_vacancy_card(vacancy, index=0, total=1)

    assert "Short AI-generated summary with pros and cons" in card
    assert "Full raw description" not in card


def test_build_vacancy_card_falls_back_to_description_when_ai_summary_is_none(make_vacancy):
    vacancy = make_vacancy(
        description="Fallback raw description",
        ai_summary=None,
    )

    card = build_vacancy_card(vacancy, index=0, total=1)

    assert "Fallback raw description" in card


def test_build_vacancy_card_truncates_long_ai_summary_to_fit_telegram_limit(make_vacancy):
    """When ai_summary exceeds Telegram limit, it is truncated with a suffix."""
    long_summary = "A" * 5000
    vacancy = make_vacancy(
        title="Dev",
        company_name="Acme",
        ai_summary=long_summary,
    )

    card = build_vacancy_card(vacancy, index=0, total=1, locale="en")

    assert len(card) <= 4096
    assert "truncated" in card or "обрезано" in card


def test_build_stats_message_escapes_html_in_vacancy_title():
    text = build_stats_message("Frontend & Backend <Dev>", 5, avg_compat=None)

    assert "Frontend &amp; Backend &lt;Dev&gt;" in text
    assert "Frontend & Backend <Dev>" not in text


def test_build_results_message_shows_all_stats():
    results = {
        "seen": 7,
        "total": 10,
        "liked": 4,
        "disliked": 3,
        "avg_compat_liked": 82.0,
    }

    text = build_results_message(results)

    assert "7" in text
    assert "10" in text
    assert "4" in text
    assert "3" in text
    assert "82" in text


def test_build_results_message_includes_ui_apply_lines_when_provided():
    results = {
        "seen": 2,
        "total": 5,
        "liked": 1,
        "disliked": 1,
        "avg_compat_liked": None,
    }
    lines = ["✅ Job A", "❌ Job B — err"]
    text = build_results_message(results, "en", ui_apply_lines=lines)
    assert "HH responses (browser)" in text
    assert "✅ Job A" in text
    assert "❌ Job B" in text


def test_format_ui_apply_result_line_success_and_error():
    ok = format_ui_apply_result_line("Dev", success=True, detail=None, locale="en")
    assert "Dev" in ok
    err = format_ui_apply_result_line("Dev", success=False, detail="ui:error", locale="en")
    assert "Dev" in err
    assert "ui:error" in err
    eq = format_ui_apply_result_line(
        "Dev",
        success=False,
        detail="ui:employer_questions",
        status="needs_employer_questions",
        locale="en",
    )
    assert "Dev" in eq
    assert "employer questions" in eq.lower()


@pytest.mark.asyncio
async def test_advance_feed_index_only_increments_index(make_feed_session):
    mock_session = AsyncMock()
    feed_session = make_feed_session(liked_ids=[1], disliked_ids=[], current_index=2)

    with patch("src.bot.modules.autoparse.feed_services.VacancyFeedSessionRepository") as mock_repo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.update = AsyncMock(return_value=feed_session)
        mock_repo.return_value = mock_repo_instance

        await advance_feed_index(mock_session, feed_session)

    call_kwargs = mock_repo_instance.update.call_args.kwargs
    assert call_kwargs["current_index"] == 3
    assert "liked_ids" not in call_kwargs


def test_build_results_message_omits_avg_compat_line_when_none():
    results = {
        "seen": 3,
        "total": 5,
        "liked": 0,
        "disliked": 3,
        "avg_compat_liked": None,
    }

    text = build_results_message(results)

    assert "feed-results-avg-liked-compat" not in text


# ── Async service tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_feed_session_stores_vacancy_ids():
    mock_session = AsyncMock()
    mock_feed_session = MagicMock()
    mock_feed_session.id = 99

    with patch("src.bot.modules.autoparse.feed_services.VacancyFeedSessionRepository") as mock_repo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.create = AsyncMock(return_value=mock_feed_session)
        mock_repo.return_value = mock_repo_instance

        result = await create_feed_session(
            session=mock_session,
            user_id=1,
            company_id=2,
            chat_id=100,
            vacancy_ids=[10, 20, 30],
        )

    mock_repo_instance.create.assert_called_once()
    call_kwargs = mock_repo_instance.create.call_args.kwargs
    assert call_kwargs["vacancy_ids"] == [10, 20, 30]
    assert call_kwargs["user_id"] == 1
    assert result.id == 99


@pytest.mark.asyncio
async def test_record_like_appends_to_liked_ids(make_feed_session):
    mock_session = AsyncMock()
    feed_session = make_feed_session(liked_ids=[], disliked_ids=[], current_index=0)

    with patch("src.bot.modules.autoparse.feed_services.VacancyFeedSessionRepository") as mock_repo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.update = AsyncMock(return_value=feed_session)
        mock_repo.return_value = mock_repo_instance

        await record_reaction(mock_session, feed_session, vacancy_id=5, is_like=True)

    call_kwargs = mock_repo_instance.update.call_args.kwargs
    assert 5 in call_kwargs["liked_ids"]
    assert call_kwargs["disliked_ids"] == []
    assert call_kwargs["current_index"] == 1


@pytest.mark.asyncio
async def test_record_dislike_appends_to_disliked_ids(make_feed_session):
    mock_session = AsyncMock()
    feed_session = make_feed_session(liked_ids=[], disliked_ids=[], current_index=0)

    with patch("src.bot.modules.autoparse.feed_services.VacancyFeedSessionRepository") as mock_repo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.update = AsyncMock(return_value=feed_session)
        mock_repo.return_value = mock_repo_instance

        await record_reaction(mock_session, feed_session, vacancy_id=7, is_like=False)

    call_kwargs = mock_repo_instance.update.call_args.kwargs
    assert 7 in call_kwargs["disliked_ids"]
    assert call_kwargs["liked_ids"] == []
    assert call_kwargs["current_index"] == 1


@pytest.mark.asyncio
async def test_get_feed_session_delegates_to_repository():
    mock_session = AsyncMock()
    expected = MagicMock()

    with patch("src.bot.modules.autoparse.feed_services.VacancyFeedSessionRepository") as mock_repo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.get_by_id = AsyncMock(return_value=expected)
        mock_repo.return_value = mock_repo_instance

        result = await get_feed_session(mock_session, session_id=42)

    mock_repo_instance.get_by_id.assert_called_once_with(42)
    assert result is expected


@pytest.mark.asyncio
async def test_move_vacancy_to_end_appends_current_id_to_end_and_increments_index(
    make_feed_session,
):
    mock_session = AsyncMock()
    feed_session = make_feed_session(
        vacancy_ids=[10, 20, 30, 40],
        current_index=1,
    )

    with patch("src.bot.modules.autoparse.feed_services.VacancyFeedSessionRepository") as mock_repo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.update = AsyncMock(return_value=feed_session)
        mock_repo.return_value = mock_repo_instance

        await move_vacancy_to_end(mock_session, feed_session)

    call_kwargs = mock_repo_instance.update.call_args.kwargs
    assert call_kwargs["vacancy_ids"] == [10, 30, 40, 20]
    assert call_kwargs["current_index"] == 2


@pytest.mark.asyncio
async def test_move_vacancy_to_end_when_only_one_vacancy_keeps_it_at_end_and_exceeds_index(
    make_feed_session,
):
    mock_session = AsyncMock()
    feed_session = make_feed_session(
        vacancy_ids=[99],
        current_index=0,
    )

    with patch("src.bot.modules.autoparse.feed_services.VacancyFeedSessionRepository") as mock_repo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.update = AsyncMock(return_value=feed_session)
        mock_repo.return_value = mock_repo_instance

        await move_vacancy_to_end(mock_session, feed_session)

    call_kwargs = mock_repo_instance.update.call_args.kwargs
    assert call_kwargs["vacancy_ids"] == [99]
    assert call_kwargs["current_index"] == 1


@pytest.mark.asyncio
async def test_complete_feed_session_sets_is_completed(make_feed_session):
    mock_session = AsyncMock()
    feed_session = make_feed_session(is_completed=False)

    with patch("src.bot.modules.autoparse.feed_services.VacancyFeedSessionRepository") as mock_repo:
        mock_repo_instance = AsyncMock()
        mock_repo_instance.update = AsyncMock(return_value=feed_session)
        mock_repo.return_value = mock_repo_instance

        await complete_feed_session(mock_session, feed_session)

    call_kwargs = mock_repo_instance.update.call_args.kwargs
    assert call_kwargs["is_completed"] is True
    assert call_kwargs["completed_at"] is not None
