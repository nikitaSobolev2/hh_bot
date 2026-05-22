from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.hh.parse_browser_session import (
    list_parse_ready_accounts,
    resolve_web_storage,
    search_url_resume_id,
)


class TestSearchUrlResumeId:
    def test_returns_resume_id_when_present(self):
        url = "https://hh.ru/search/vacancy?text=python&resume=abc123"
        assert search_url_resume_id(url) == "abc123"

    def test_returns_none_when_missing(self):
        assert search_url_resume_id("https://hh.ru/search/vacancy?text=python") is None

    def test_returns_none_for_invalid_url(self):
        assert search_url_resume_id("not-a-url") is None


class TestListParseReadyAccounts:
    @pytest.mark.asyncio
    async def test_filters_accounts_with_browser_storage(self):
        ready = MagicMock(browser_storage_enc=b"enc")
        not_ready = MagicMock(browser_storage_enc=None)
        session = AsyncMock()
        with patch(
            "src.services.hh.parse_browser_session.HhLinkedAccountRepository"
        ) as repo_cls:
            repo = repo_cls.return_value
            repo.list_active_for_user = AsyncMock(return_value=[ready, not_ready])
            result = await list_parse_ready_accounts(session, user_id=1)
        assert result == [ready]


class TestResolveWebStorage:
    @pytest.mark.asyncio
    async def test_returns_none_when_account_missing(self):
        session = AsyncMock()
        with patch(
            "src.services.hh.parse_browser_session.HhLinkedAccountRepository"
        ) as repo_cls:
            repo = repo_cls.return_value
            repo.get_by_id = AsyncMock(return_value=None)
            result = await resolve_web_storage(session, user_id=1, account_id=99)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_decrypted_storage_for_valid_account(self):
        account = MagicMock(user_id=1, browser_storage_enc=b"enc")
        session = AsyncMock()
        with (
            patch(
                "src.services.hh.parse_browser_session.HhLinkedAccountRepository"
            ) as repo_cls,
            patch("src.services.hh.parse_browser_session.HhTokenCipher"),
            patch(
                "src.services.hh.parse_browser_session.decrypt_browser_storage",
                return_value={"cookies": []},
            ),
            patch(
                "src.services.hh.parse_browser_session.settings.hh_token_encryption_key",
                "test-key",
            ),
        ):
            repo = repo_cls.return_value
            repo.get_by_id = AsyncMock(return_value=account)
            result = await resolve_web_storage(session, user_id=1, account_id=5)
        assert result == {"cookies": []}
