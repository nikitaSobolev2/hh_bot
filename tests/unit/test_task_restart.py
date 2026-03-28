"""Unit tests for task restart service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services import task_restart
from src.services.task_restart import restart_pending_parsing_tasks


def _make_company(company_id: int = 1, user_id: int = 42, telegram_id: int = 123456) -> MagicMock:
    company = MagicMock()
    company.id = company_id
    company.user_id = user_id
    user = MagicMock()
    user.telegram_id = telegram_id
    company.user = user
    return company


class TestRestartPendingParsingTasks:
    @pytest.mark.asyncio
    async def test_returns_zero_when_parsing_disabled(self):
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)

        settings_repo = MagicMock()
        settings_repo.get_value = AsyncMock(return_value=False)

        company_repo = MagicMock()
        company_repo.get_pending_or_processing = AsyncMock(return_value=[])

        session_factory = MagicMock()
        session_factory.return_value = session

        with (
            patch("src.services.task_restart.async_session_factory", session_factory),
            patch(
                "src.services.task_restart.AppSettingRepository",
                return_value=settings_repo,
            ),
            patch(
                "src.services.task_restart.ParsingCompanyRepository",
                return_value=company_repo,
            ),
        ):
            result = await restart_pending_parsing_tasks()

        assert result == 0
        company_repo.get_pending_or_processing.assert_not_called()

    @pytest.mark.asyncio
    async def test_enqueues_pending_companies_with_correct_args(self):
        company1 = _make_company(company_id=1, user_id=42, telegram_id=111)
        company2 = _make_company(company_id=2, user_id=99, telegram_id=222)

        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)

        settings_repo = MagicMock()
        settings_repo.get_value = AsyncMock(return_value=True)

        company_repo = MagicMock()
        company_repo.get_pending_or_processing = AsyncMock(return_value=[company1, company2])

        session_factory = MagicMock()
        session_factory.return_value = session

        run_celery_task_calls: list[tuple] = []

        async def capture_run_celery_task(task, *args, **kwargs):
            run_celery_task_calls.append((task, args, kwargs))

        with (
            patch("src.services.task_restart.async_session_factory", session_factory),
            patch(
                "src.services.task_restart.AppSettingRepository",
                return_value=settings_repo,
            ),
            patch(
                "src.services.task_restart.ParsingCompanyRepository",
                return_value=company_repo,
            ),
            patch(
                "src.services.task_restart.run_celery_task",
                new=capture_run_celery_task,
            ),
        ):
            result = await restart_pending_parsing_tasks()

        assert result == 2
        assert len(run_celery_task_calls) == 2

        from src.worker.tasks.parsing import run_parsing_company

        call1 = run_celery_task_calls[0]
        assert call1[0] is run_parsing_company
        assert call1[1] == (1, 42)
        assert call1[2] == {"include_blacklisted": False, "telegram_chat_id": 111}

        call2 = run_celery_task_calls[1]
        assert call2[0] is run_parsing_company
        assert call2[1] == (2, 99)
        assert call2[2] == {"include_blacklisted": False, "telegram_chat_id": 222}

    @pytest.mark.asyncio
    async def test_skips_company_with_missing_user(self):
        company = _make_company()
        company.user = None

        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)

        settings_repo = MagicMock()
        settings_repo.get_value = AsyncMock(return_value=True)

        company_repo = MagicMock()
        company_repo.get_pending_or_processing = AsyncMock(return_value=[company])

        session_factory = MagicMock()
        session_factory.return_value = session

        run_celery_task_calls: list = []

        async def capture_run_celery_task(*args, **kwargs):
            run_celery_task_calls.append(1)

        with (
            patch("src.services.task_restart.async_session_factory", session_factory),
            patch(
                "src.services.task_restart.AppSettingRepository",
                return_value=settings_repo,
            ),
            patch(
                "src.services.task_restart.ParsingCompanyRepository",
                return_value=company_repo,
            ),
            patch(
                "src.services.task_restart.run_celery_task",
                new=capture_run_celery_task,
            ),
        ):
            result = await restart_pending_parsing_tasks()

        assert result == 0
        assert len(run_celery_task_calls) == 0

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_pending_companies(self):
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)

        settings_repo = MagicMock()
        settings_repo.get_value = AsyncMock(return_value=True)

        company_repo = MagicMock()
        company_repo.get_pending_or_processing = AsyncMock(return_value=[])

        session_factory = MagicMock()
        session_factory.return_value = session

        with (
            patch("src.services.task_restart.async_session_factory", session_factory),
            patch(
                "src.services.task_restart.AppSettingRepository",
                return_value=settings_repo,
            ),
            patch(
                "src.services.task_restart.ParsingCompanyRepository",
                return_value=company_repo,
            ),
        ):
            result = await restart_pending_parsing_tasks()

        assert result == 0


class TestParseHhUiCheckpointKey:
    def test_splits_chat_id_and_task_key_with_colons(self) -> None:
        assert task_restart._parse_hh_ui_checkpoint_key(
            "checkpoint:hh_ui_apply_batch:12345:autorespond:77:celeryid"
        ) == (12345, "autorespond:77:celeryid")

    def test_returns_none_for_bad_prefix(self) -> None:
        assert task_restart._parse_hh_ui_checkpoint_key("other:key") is None


