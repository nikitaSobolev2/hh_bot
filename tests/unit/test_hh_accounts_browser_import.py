"""Tests for browser storage_state import (HH accounts)."""

import json
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet


@pytest.mark.asyncio
async def test_browser_import_reactivates_revoked_row(monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-import must clear revoked_at so list_active_for_user shows the account again."""
    from src.bot.modules.hh_accounts.handlers import hh_browser_import_document

    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(
        "src.bot.modules.hh_accounts.handlers.settings.hh_token_encryption_key",
        key,
    )
    monkeypatch.setattr(
        "src.bot.modules.hh_accounts.handlers.settings.hh_ui_apply_enabled",
        True,
    )

    payload = {
        "cookies": [{"domain": ".hh.ru", "name": "uid", "value": "42"}],
        "origins": [],
    }

    def fake_download(_doc, destination: BytesIO) -> None:
        destination.write(json.dumps(payload).encode("utf-8"))
        destination.seek(0)

    message = MagicMock()
    message.document = MagicMock()
    message.document.file_name = "hh_browser_storage_state.json"
    message.bot.download = AsyncMock(side_effect=fake_download)
    message.answer = AsyncMock()

    user = MagicMock()
    user.id = 7

    session = MagicMock()
    session.commit = AsyncMock()

    state = MagicMock()
    state.clear = AsyncMock()

    i18n = MagicMock()
    i18n.get.return_value = "ok"

    existing = MagicMock()
    repo_inst = MagicMock()
    repo_inst.get_by_user_and_hh_user_id = AsyncMock(return_value=existing)
    repo_inst.update = AsyncMock()
    repo_inst.create = AsyncMock()

    with (
        patch(
            "src.services.hh.linked_account_browser_storage.HhLinkedAccountRepository",
            return_value=repo_inst,
        ),
        patch(
            "src.bot.modules.hh_accounts.handlers._hub_message",
            new_callable=AsyncMock,
            return_value=("hub", MagicMock()),
        ),
    ):
        await hh_browser_import_document(message, session, user, state, i18n)

    repo_inst.create.assert_not_called()
    repo_inst.update.assert_called_once()
    _args, kwargs = repo_inst.update.call_args
    assert _args[0] is existing
    assert kwargs.get("revoked_at") is None
    assert kwargs.get("browser_storage_enc") is not None
    assert kwargs.get("browser_storage_updated_at") is not None
    assert kwargs.get("last_used_at") is not None
