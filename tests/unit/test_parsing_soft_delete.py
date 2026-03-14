"""Unit tests for parsing soft delete."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestParsingCompanyRepositorySoftDelete:
    @pytest.mark.asyncio
    async def test_soft_delete_sets_is_deleted_true(self):
        from src.repositories.parsing import ParsingCompanyRepository

        company = MagicMock()
        company.is_deleted = False

        session = AsyncMock()
        repo = ParsingCompanyRepository(session)
        repo.get_by_id = AsyncMock(return_value=company)
        repo.update = AsyncMock()

        await repo.soft_delete(42)

        repo.get_by_id.assert_awaited_once_with(42)
        repo.update.assert_awaited_once_with(company, is_deleted=True)

    @pytest.mark.asyncio
    async def test_soft_delete_skips_when_company_not_found(self):
        from src.repositories.parsing import ParsingCompanyRepository

        session = AsyncMock()
        repo = ParsingCompanyRepository(session)
        repo.get_by_id = AsyncMock(return_value=None)
        repo.update = AsyncMock()

        await repo.soft_delete(99)

        repo.get_by_id.assert_awaited_once_with(99)
        repo.update.assert_not_awaited()


class TestParsingServiceSoftDelete:
    @pytest.mark.asyncio
    async def test_soft_delete_parsing_returns_true_when_deleted(self):
        from src.bot.modules.parsing import services as parsing_service

        session = AsyncMock()
        session.commit = AsyncMock()

        with patch(
            "src.bot.modules.parsing.services.ParsingCompanyRepository"
        ) as mock_repo_cls:
            repo = AsyncMock()
            company = MagicMock()
            repo.get_by_id_for_user = AsyncMock(return_value=company)
            repo.soft_delete = AsyncMock()
            mock_repo_cls.return_value = repo

            result = await parsing_service.soft_delete_parsing(session, 1, 42)

        assert result is True
        repo.get_by_id_for_user.assert_awaited_once_with(1, 42)
        repo.soft_delete.assert_awaited_once_with(1)
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_soft_delete_parsing_returns_false_when_not_found(self):
        from src.bot.modules.parsing import services as parsing_service

        session = AsyncMock()

        with patch(
            "src.bot.modules.parsing.services.ParsingCompanyRepository"
        ) as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_id_for_user = AsyncMock(return_value=None)
            repo.soft_delete = AsyncMock()
            mock_repo_cls.return_value = repo

            result = await parsing_service.soft_delete_parsing(session, 99, 42)

        assert result is False
        repo.get_by_id_for_user.assert_awaited_once_with(99, 42)
        repo.soft_delete.assert_not_awaited()


class TestParsingTaskSkipsDeleted:
    @pytest.mark.asyncio
    async def test_run_parsing_returns_deleted_when_company_is_deleted(self):
        from src.worker.tasks.parsing import _run_parsing_company_async

        company = MagicMock()
        company.is_deleted = True
        company.vacancy_title = "Test"
        company.search_url = "https://hh.ru/search"
        company.keyword_filter = ""
        company.target_count = 10
        company.use_compatibility_check = False
        company.compatibility_threshold = None

        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        session_factory = MagicMock(return_value=session)

        company_repo = AsyncMock()
        company_repo.get_by_id = AsyncMock(return_value=company)
        company_repo.update = AsyncMock()

        task_repo = AsyncMock()
        task_repo.get_by_idempotency_key = AsyncMock(return_value=None)

        settings_repo = AsyncMock()
        settings_repo.get_value = AsyncMock(return_value=True)

        with (
            patch(
                "src.worker.tasks.parsing._init_bot_and_locale",
                new=AsyncMock(return_value=(None, "ru")),
            ),
            patch(
                "src.worker.circuit_breaker.CircuitBreaker.is_call_allowed",
                return_value=True,
            ),
            patch(
                "src.repositories.app_settings.AppSettingRepository",
                return_value=settings_repo,
            ),
            patch(
                "src.repositories.parsing.ParsingCompanyRepository",
                return_value=company_repo,
            ),
            patch("src.repositories.task.CeleryTaskRepository", return_value=task_repo),
        ):
            fake_task = MagicMock()
            fake_task.request.id = "test-id"

            result = await _run_parsing_company_async(
                session_factory,
                fake_task,
                parsing_company_id=1,
                user_id=42,
                include_blacklisted=False,
                telegram_chat_id=0,
            )

        assert result == {"status": "deleted"}
        company_repo.update.assert_not_awaited()
