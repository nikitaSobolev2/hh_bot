"""Unit tests for the vacancy summary (about-me) generation task."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_session_factory():
    session = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory, session


@pytest.fixture
def mock_task():
    task = MagicMock()
    task.check_enabled = AsyncMock(return_value=True)
    task.load_circuit_breaker = AsyncMock()
    task.is_already_completed = AsyncMock(return_value=False)
    task.mark_completed = AsyncMock()
    task.create_bot = MagicMock(return_value=AsyncMock())
    task.notify_user = AsyncMock()

    cb = MagicMock()
    cb.is_call_allowed = MagicMock(return_value=True)
    cb.record_success = MagicMock()
    cb.record_failure = MagicMock()
    task.load_circuit_breaker.return_value = cb

    return task, cb


class TestVacancySummaryTaskGuards:
    @pytest.mark.asyncio
    async def test_returns_disabled_when_feature_flag_off(self, mock_session_factory, mock_task):
        from src.worker.tasks.vacancy_summary import _generate_summary_async

        factory, _ = mock_session_factory
        task, _ = mock_task
        task.check_enabled.return_value = False

        result = await _generate_summary_async(
            task, factory, 1, 1, None, None, None, None, 100, 200, "ru"
        )
        assert result["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_returns_circuit_open_when_breaker_open(self, mock_session_factory, mock_task):
        from src.worker.tasks.vacancy_summary import _generate_summary_async

        factory, _ = mock_session_factory
        task, cb = mock_task
        cb.is_call_allowed.return_value = False

        result = await _generate_summary_async(
            task, factory, 1, 1, None, None, None, None, 100, 200, "ru"
        )
        assert result["status"] == "circuit_open"

    @pytest.mark.asyncio
    async def test_returns_already_completed_on_duplicate(self, mock_session_factory, mock_task):
        from src.worker.tasks.vacancy_summary import _generate_summary_async

        factory, _ = mock_session_factory
        task, _ = mock_task
        task.is_already_completed.return_value = True

        result = await _generate_summary_async(
            task, factory, 1, 1, None, None, None, None, 100, 200, "ru"
        )
        assert result["status"] == "already_completed"


class TestVacancySummaryIdempotencyKey:
    """Verify idempotency key is constructed correctly."""

    @pytest.mark.asyncio
    async def test_idempotency_key_includes_summary_id(self, mock_session_factory, mock_task):
        from src.worker.tasks.vacancy_summary import _generate_summary_async

        factory, _ = mock_session_factory
        task, _ = mock_task
        task.is_already_completed.return_value = True

        await _generate_summary_async(
            task,
            factory,
            summary_id=42,
            user_id=1,
            excluded_industries=None,
            location=None,
            remote_preference=None,
            additional_notes=None,
            chat_id=100,
            message_id=200,
            locale="ru",
        )

        call_args = task.is_already_completed.call_args[0]
        assert "42" in call_args[0]


class TestStripAgentWrapper:
    """Verify _strip_agent_wrapper removes intro/outro, keeps only summary content."""

    def test_strips_leading_intro_and_trailing_outro(self):
        from src.worker.tasks.vacancy_summary import _strip_agent_wrapper

        raw = (
            "Вот профессиональный текст «О себе» для вашего резюме, "
            "составленный на основе данных:\n\n"
            "---\n\n"
            "Я Senior Fullstack разработчик с 5-летним опытом.\n\n"
            "🔥 Как достигаю результата\n"
            "Строю архитектуру.\n\n"
            "---\n\n"
            "Если хотите, я могу подготовить ещё более «продающий» вариант под LinkedIn. "
            "Хотите, чтобы я так сделал?"
        )
        result = _strip_agent_wrapper(raw)
        assert "Вот профессиональный" not in result
        assert "Если хотите" not in result
        assert "Хотите, чтобы" not in result
        assert result.startswith("Я Senior")
        assert "🔥 Как достигаю" in result

    def test_preserves_clean_summary_unchanged(self):
        from src.worker.tasks.vacancy_summary import _strip_agent_wrapper

        clean = "Я Senior разработчик.\n\n🔥 Как достигаю результата\nСтрою архитектуру."
        assert _strip_agent_wrapper(clean) == clean

    def test_strips_only_outro_when_no_intro(self):
        from src.worker.tasks.vacancy_summary import _strip_agent_wrapper

        raw = "Я Senior разработчик.\n\nЕсли хотите, могу подготовить вариант под LinkedIn."
        result = _strip_agent_wrapper(raw)
        assert result == "Я Senior разработчик."

    def test_keeps_russian_sections_when_english_preamble_before_separator(self):
        """Do not drop content before first --- when section markers live in that part."""
        from src.worker.tasks.vacancy_summary import _strip_agent_wrapper

        raw = (
            "Here is a draft for your profile.\n\n"
            "Я Senior Backend Developer с коммерческим опытом.\n\n"
            "🔥 Как достигаю результата\n"
            "Строю микросервисы.\n\n"
            "---\n"
            "Senior backend engineer focused on distributed systems."
        )
        result = _strip_agent_wrapper(raw)
        assert "Я Senior Backend" in result
        assert "🔥 Как достигаю" in result
        assert "Senior backend engineer" in result


_VALID_ABOUT_ME = """Я Senior разработчик с опытом.

🔥 Как достигаю результата
Строю надёжные системы.

⭐️ Мне это легко
• Достижение без выдуманных метрик.

Я полезен для — продуктовых команд.

⚠️ Ограничения — не указано.

Где живу — Москва.

---
Senior engineer focused on backend systems.
"""


class TestVacancySummaryOutputMeetsFormat:
    def test_valid_russian_body_with_markers_and_english_tail(self):
        from src.worker.tasks.vacancy_summary import _vacancy_summary_output_meets_format

        assert _vacancy_summary_output_meets_format(_VALID_ABOUT_ME) is True

    def test_rejects_missing_separator(self):
        from src.worker.tasks.vacancy_summary import _vacancy_summary_output_meets_format

        assert (
            _vacancy_summary_output_meets_format(
                "Я разработчик.\n\n🔥\n\n⭐️\n\n⚠️\n\nТекст без разделителя."
            )
            is False
        )

    def test_rejects_english_only_before_separator(self):
        from src.worker.tasks.vacancy_summary import _vacancy_summary_output_meets_format

        assert (
            _vacancy_summary_output_meets_format(
                "I am a Senior developer.\n\n---\nEnglish only."
            )
            is False
        )

    def test_rejects_missing_section_markers(self):
        from src.worker.tasks.vacancy_summary import _vacancy_summary_output_meets_format

        assert (
            _vacancy_summary_output_meets_format(
                "Я разработчик в Москве.\n\n---\nI am a developer."
            )
            is False
        )

    def test_rejects_empty_tail_after_separator(self):
        from src.worker.tasks.vacancy_summary import _vacancy_summary_output_meets_format

        assert _vacancy_summary_output_meets_format("Я текст.\n\n🔥\n\n⭐️\n\n⚠️\n\n---\n") is False


@pytest.mark.asyncio
async def test_generate_summary_retries_once_when_first_invalid(mock_session_factory, mock_task):
    """First model output invalid (English-only); second output valid — two API calls."""
    from src.worker.tasks.vacancy_summary import _generate_summary_async

    factory, _session = mock_session_factory
    task, cb = mock_task

    exp = MagicMock()
    exp.company_name = "ACME"
    exp.stack = "Python"
    exp.title = "Dev"
    exp.period = "2020"
    exp.achievements = None
    exp.duties = None

    mock_we_repo = MagicMock()
    mock_we_repo.get_active_by_user = AsyncMock(return_value=[exp])

    summary = MagicMock()
    mock_vs_repo = MagicMock()
    mock_vs_repo.get_by_id = AsyncMock(return_value=summary)
    mock_vs_repo.update_text = AsyncMock()

    invalid = "I am a Senior Fullstack-Developer with over 5 years. No Russian structure."
    valid = _VALID_ABOUT_ME

    with (
        patch(
            "src.repositories.work_experience.WorkExperienceRepository",
            return_value=mock_we_repo,
        ),
        patch(
            "src.repositories.vacancy_summary.VacancySummaryRepository",
            return_value=mock_vs_repo,
        ),
        patch(
            "src.bot.modules.autoparse.services.derive_tech_stack_from_experiences",
            return_value=["Python"],
        ),
        patch("src.services.ai.client.AIClient") as mock_ai_cls,
        patch("src.core.i18n.get_text", return_value="RETRY"),
    ):
        mock_ai_cls.return_value.generate_text = AsyncMock(side_effect=[invalid, valid])

        await _generate_summary_async(
            task,
            factory,
            summary_id=1,
            user_id=1,
            excluded_industries=None,
            location=None,
            remote_preference=None,
            additional_notes=None,
            chat_id=100,
            message_id=200,
            locale="ru",
            context="",
        )

    assert mock_ai_cls.return_value.generate_text.await_count == 2
    mock_vs_repo.update_text.assert_called_once()
    assert cb.record_success.call_count == 2


@pytest.mark.asyncio
async def test_generate_summary_logs_warning_when_both_outputs_invalid(
    mock_session_factory,
    mock_task,
):
    from src.worker.tasks.vacancy_summary import _generate_summary_async

    factory, _ = mock_session_factory
    task, _cb = mock_task

    exp = MagicMock()
    exp.company_name = "ACME"
    exp.stack = "Py"
    exp.title = None
    exp.period = None
    exp.achievements = None
    exp.duties = None

    mock_we_repo = MagicMock()
    mock_we_repo.get_active_by_user = AsyncMock(return_value=[exp])

    summary = MagicMock()
    mock_vs_repo = MagicMock()
    mock_vs_repo.get_by_id = AsyncMock(return_value=summary)
    mock_vs_repo.update_text = AsyncMock()

    bad = "English only paragraph without markers."

    with (
        patch(
            "src.repositories.work_experience.WorkExperienceRepository",
            return_value=mock_we_repo,
        ),
        patch(
            "src.repositories.vacancy_summary.VacancySummaryRepository",
            return_value=mock_vs_repo,
        ),
        patch(
            "src.bot.modules.autoparse.services.derive_tech_stack_from_experiences",
            return_value=["Py"],
        ),
        patch("src.services.ai.client.AIClient") as mock_ai_cls,
        patch("src.core.i18n.get_text", return_value="RETRY"),
    ):
        mock_ai_cls.return_value.generate_text = AsyncMock(side_effect=[bad, bad])

        await _generate_summary_async(
            task,
            factory,
            summary_id=2,
            user_id=1,
            excluded_industries=None,
            location=None,
            remote_preference=None,
            additional_notes=None,
            chat_id=100,
            message_id=200,
            locale="en",
            context="",
        )

    mock_vs_repo.update_text.assert_called_once()
    call_text = mock_vs_repo.update_text.call_args[0][1]
    assert "English only" in call_text
