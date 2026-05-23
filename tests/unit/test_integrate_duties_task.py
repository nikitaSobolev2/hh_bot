"""Unit tests for integrate duties Celery task."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_session_factory():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    factory = MagicMock(return_value=ctx)
    return factory, session


@pytest.mark.asyncio
async def test_integrate_duties_async_returns_disabled_when_flag_off(
    mock_session_factory,
):
    from src.worker.tasks.integrate_duties import _integrate_duties_async

    factory, _session = mock_session_factory
    settings_repo = MagicMock()
    settings_repo.get_value = AsyncMock(return_value=False)

    with patch(
        "src.repositories.app_settings.AppSettingRepository",
        return_value=settings_repo,
    ):
        result = await _integrate_duties_async(
            factory,
            MagicMock(request=MagicMock(id="task-1")),
            parsing_company_id=1,
            user_id=2,
            telegram_chat_id=3,
        )

    assert result == {"status": "disabled"}


@pytest.mark.asyncio
async def test_integrate_duties_async_parses_and_saves_payload(mock_session_factory):
    from src.worker.tasks.integrate_duties import _integrate_duties_async

    factory, session = mock_session_factory

    company = MagicMock()
    company.vacancy_title = "Python Dev"

    agg = MagicMock()
    agg.top_keywords = {"Django": 5, "PostgreSQL": 3}
    agg.integrated_duties = None

    work_exp = MagicMock()
    work_exp.id = 10
    work_exp.company_name = "Acme"
    work_exp.stack = "Python"
    work_exp.title = "Backend"
    work_exp.period = "2020-2023"
    work_exp.achievements = None
    work_exp.duties = "- Built APIs"

    settings_repo = MagicMock()
    settings_repo.get_value = AsyncMock(side_effect=lambda key, default=None: default)

    company_repo = MagicMock()
    company_repo.get_by_id = AsyncMock(return_value=company)

    agg_repo = MagicMock()
    agg_repo.get_by_company = AsyncMock(return_value=agg)

    we_repo = MagicMock()
    we_repo.get_active_by_user = AsyncMock(return_value=[work_exp])

    user_repo = MagicMock()
    user = MagicMock()
    user.language_code = "en"
    user_repo.get_by_id = AsyncMock(return_value=user)

    task_repo = MagicMock()
    task_repo.get_by_idempotency_key = AsyncMock(return_value=None)

    ai_client = MagicMock()
    ai_client.generate_text = AsyncMock(
        return_value='{"work_experiences":[{"work_exp_id":10,"duties":["Used Django daily"]}]}'
    )

    bot = MagicMock()
    bot.session.close = AsyncMock()

    cb = MagicMock()
    cb.is_call_allowed.return_value = True

    with (
        patch(
            "src.repositories.app_settings.AppSettingRepository",
            return_value=settings_repo,
        ),
        patch(
            "src.repositories.parsing.ParsingCompanyRepository",
            return_value=company_repo,
        ),
        patch(
            "src.repositories.parsing.AggregatedResultRepository",
            return_value=agg_repo,
        ),
        patch(
            "src.repositories.work_experience.WorkExperienceRepository",
            return_value=we_repo,
        ),
        patch(
            "src.repositories.user.UserRepository",
            return_value=user_repo,
        ),
        patch(
            "src.repositories.task.CeleryTaskRepository",
            return_value=task_repo,
        ),
        patch("src.services.ai.client.AIClient", return_value=ai_client),
        patch("src.services.ai.client.close_ai_client", new=AsyncMock()),
        patch("src.worker.circuit_breaker.CircuitBreaker", return_value=cb),
        patch("aiogram.Bot", return_value=bot),
        patch(
            "src.worker.tasks.integrate_duties._notify_user",
            new=AsyncMock(),
        ),
        patch(
            "src.worker.tasks.integrate_duties._save_task_record",
            new=AsyncMock(),
        ),
    ):
        result = await _integrate_duties_async(
            factory,
            MagicMock(request=MagicMock(id="task-2")),
            parsing_company_id=1,
            user_id=2,
            telegram_chat_id=3,
        )

    assert result["status"] == "completed"
    assert agg.integrated_duties is not None
    assert agg.integrated_duties["work_experiences"][0]["company_name"] == "Acme"
    session.commit.assert_awaited()
