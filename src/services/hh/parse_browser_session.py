"""Shared helpers for HH browser session used during vacancy parsing."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.logging import get_logger
from src.models.hh_linked_account import HhLinkedAccount
from src.repositories.hh_linked_account import HhLinkedAccountRepository
from src.services.hh.crypto import HhTokenCipher
from src.services.hh_ui.storage import decrypt_browser_storage

logger = get_logger(__name__)


def search_url_resume_id(url: str) -> str | None:
    """Return resume id from HH search URL query param, if present."""
    try:
        values = parse_qs(urlparse(url).query).get("resume") or []
    except ValueError:
        return None
    for value in values:
        resume_id = value.strip()
        if resume_id:
            return resume_id
    return None


async def list_parse_ready_accounts(
    session: AsyncSession,
    user_id: int,
) -> list[HhLinkedAccount]:
    """Active linked accounts that have encrypted browser storage."""
    hh_repo = HhLinkedAccountRepository(session)
    accounts = await hh_repo.list_active_for_user(user_id)
    return [acc for acc in accounts if acc.browser_storage_enc]


async def resolve_web_storage(
    session: AsyncSession,
    *,
    user_id: int,
    account_id: int,
) -> dict[str, Any] | None:
    """Load and decrypt browser storage for a user's linked HH account."""
    hh_repo = HhLinkedAccountRepository(session)
    hh_acc = await hh_repo.get_by_id(account_id)
    if not hh_acc or hh_acc.user_id != user_id or not hh_acc.browser_storage_enc:
        return None
    if not settings.hh_token_encryption_key:
        return None
    try:
        cipher = HhTokenCipher(settings.hh_token_encryption_key)
        return decrypt_browser_storage(hh_acc.browser_storage_enc, cipher)
    except Exception as exc:
        logger.warning(
            "Failed to decrypt browser storage",
            account_id=account_id,
            user_id=user_id,
            error=str(exc)[:200],
        )
        return None
