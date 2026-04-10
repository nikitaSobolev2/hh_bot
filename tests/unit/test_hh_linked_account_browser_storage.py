"""Tests for linked-account browser storage persistence outcomes."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from src.services.hh.crypto import HhTokenCipher
from src.services.hh.linked_account_browser_storage import (
    BrowserStoragePersistOutcome,
    persist_browser_storage_for_linked_account,
)


def _logged_in_state(uid: str) -> dict:
    return {
        "cookies": [{"domain": ".hh.ru", "name": "uid", "value": uid}],
        "origins": [],
    }


@pytest.mark.asyncio
async def test_replace_session_updates_target_when_identity_matches() -> None:
    session = MagicMock()
    cipher = HhTokenCipher(Fernet.generate_key().decode("ascii"))
    target = SimpleNamespace(id=10, user_id=7, hh_user_id="42")
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=target)
    repo.get_by_user_and_hh_user_id = AsyncMock(return_value=target)
    repo.update = AsyncMock(return_value=target)
    repo.clear_resume_list_cache = AsyncMock()

    with patch(
        "src.services.hh.linked_account_browser_storage.HhLinkedAccountRepository",
        return_value=repo,
    ):
        result = await persist_browser_storage_for_linked_account(
            session,
            7,
            10,
            _logged_in_state("42"),
            cipher=cipher,
        )

    assert result.outcome == BrowserStoragePersistOutcome.UPDATED_TARGET
    repo.update.assert_awaited_once()
    assert repo.update.await_args.args[0] is target
    assert "hh_user_id" not in repo.update.await_args.kwargs


@pytest.mark.asyncio
async def test_replace_session_updates_matching_other_account_when_identity_differs() -> None:
    session = MagicMock()
    cipher = HhTokenCipher(Fernet.generate_key().decode("ascii"))
    target = SimpleNamespace(id=10, user_id=7, hh_user_id="42")
    other = SimpleNamespace(id=11, user_id=7, hh_user_id="99")
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=target)
    repo.get_by_user_and_hh_user_id = AsyncMock(return_value=other)
    repo.update = AsyncMock(return_value=other)
    repo.clear_resume_list_cache = AsyncMock()

    with patch(
        "src.services.hh.linked_account_browser_storage.HhLinkedAccountRepository",
        return_value=repo,
    ):
        result = await persist_browser_storage_for_linked_account(
            session,
            7,
            10,
            _logged_in_state("99"),
            cipher=cipher,
        )

    assert result.outcome == BrowserStoragePersistOutcome.UPDATED_OTHER_EXISTING
    assert result.account_id == 11
    repo.update.assert_awaited_once()
    assert repo.update.await_args.args[0] is other
    assert "hh_user_id" not in repo.update.await_args.kwargs


@pytest.mark.asyncio
async def test_replace_session_moves_target_identity_when_new_identity_not_linked() -> None:
    session = MagicMock()
    cipher = HhTokenCipher(Fernet.generate_key().decode("ascii"))
    target = SimpleNamespace(id=10, user_id=7, hh_user_id="42")
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=target)
    repo.get_by_user_and_hh_user_id = AsyncMock(return_value=None)
    repo.update = AsyncMock(return_value=target)
    repo.clear_resume_list_cache = AsyncMock()

    with patch(
        "src.services.hh.linked_account_browser_storage.HhLinkedAccountRepository",
        return_value=repo,
    ):
        result = await persist_browser_storage_for_linked_account(
            session,
            7,
            10,
            _logged_in_state("99"),
            cipher=cipher,
        )

    assert result.outcome == BrowserStoragePersistOutcome.UPDATED_TARGET_IDENTITY
    assert repo.update.await_args.kwargs["hh_user_id"] == "99"


def test_validate_logged_in_storage_rejects_not_logged_in_state() -> None:
    from src.services.hh_ui.browser_link import validate_logged_in_playwright_storage_state

    with pytest.raises(ValueError, match="not-logged-in"):
        validate_logged_in_playwright_storage_state(
            {"cookies": [{"domain": ".hh.ru", "name": "landing", "value": "anon"}], "origins": []}
        )
