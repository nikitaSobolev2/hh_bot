"""Persist encrypted Playwright storage_state into hh_linked_accounts (OAuth + browser UI)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.hh_linked_account import HhLinkedAccountRepository
from src.services.hh.crypto import HhTokenCipher
from src.services.hh_ui.browser_link import (
    encrypt_storage_for_account,
    make_hh_user_id_for_browser_link,
    placeholder_access_expires_at,
    placeholder_token_ciphertexts,
    validate_logged_in_playwright_storage_state,
)


def utc_naive_now() -> datetime:
    from datetime import UTC

    return datetime.now(UTC).replace(tzinfo=None)


class BrowserStoragePersistOutcome(str, Enum):
    CREATED = "created"
    UPDATED_EXISTING = "updated_existing"
    UPDATED_TARGET = "updated_target"
    UPDATED_TARGET_IDENTITY = "updated_target_identity"
    UPDATED_OTHER_EXISTING = "updated_other_existing"


@dataclass(frozen=True, slots=True)
class BrowserStoragePersistResult:
    outcome: BrowserStoragePersistOutcome
    account_id: int
    hh_user_id: str
    requested_account_id: int | None = None


async def persist_browser_storage_state_for_user(
    db_session: AsyncSession,
    user_id: int,
    state_dict: dict[str, Any],
    *,
    cipher: HhTokenCipher,
) -> BrowserStoragePersistResult:
    """Create or update a linked row with browser storage; reactivates revoked rows."""
    state_dict = validate_logged_in_playwright_storage_state(state_dict)
    enc_storage = encrypt_storage_for_account(state_dict, cipher)
    hh_uid = make_hh_user_id_for_browser_link(state_dict)
    now = utc_naive_now()

    repo = HhLinkedAccountRepository(db_session)
    existing = await repo.get_by_user_and_hh_user_id(user_id, hh_uid)
    if existing:
        acc = await repo.update(
            existing,
            browser_storage_enc=enc_storage,
            browser_storage_updated_at=now,
            revoked_at=None,
            last_used_at=now,
        )
        outcome = BrowserStoragePersistOutcome.UPDATED_EXISTING
    else:
        ph_access, ph_refresh = placeholder_token_ciphertexts(cipher)
        acc = await repo.create(
            user_id=user_id,
            hh_user_id=hh_uid,
            label=None,
            access_token_enc=ph_access,
            refresh_token_enc=ph_refresh,
            access_expires_at=placeholder_access_expires_at(),
            revoked_at=None,
            last_used_at=now,
            browser_storage_enc=enc_storage,
            browser_storage_updated_at=now,
        )
        outcome = BrowserStoragePersistOutcome.CREATED
    await repo.clear_resume_list_cache(acc)
    return BrowserStoragePersistResult(
        outcome=outcome,
        account_id=acc.id,
        hh_user_id=hh_uid,
    )


async def persist_browser_storage_for_linked_account(
    db_session: AsyncSession,
    user_id: int,
    hh_linked_account_id: int,
    state_dict: dict[str, Any],
    *,
    cipher: HhTokenCipher,
) -> BrowserStoragePersistResult:
    """Update browser session on a specific linked account row (no new row).

    Used when refreshing cookies for an existing account (e.g. server login assist “replace”).
    When the refreshed session belongs to another already-linked HH account, update that
    matching row instead of corrupting the requested row's identity.
    """
    state_dict = validate_logged_in_playwright_storage_state(state_dict)
    enc_storage = encrypt_storage_for_account(state_dict, cipher)
    new_hh_uid = make_hh_user_id_for_browser_link(state_dict)
    now = utc_naive_now()

    repo = HhLinkedAccountRepository(db_session)
    acc = await repo.get_by_id(hh_linked_account_id)
    if not acc or acc.user_id != user_id:
        raise ValueError("hh_linked_account not found or wrong user")

    if acc.hh_user_id == new_hh_uid:
        acc = await repo.update(
            acc,
            browser_storage_enc=enc_storage,
            browser_storage_updated_at=now,
            revoked_at=None,
            last_used_at=now,
        )
        await repo.clear_resume_list_cache(acc)
        return BrowserStoragePersistResult(
            outcome=BrowserStoragePersistOutcome.UPDATED_TARGET,
            account_id=acc.id,
            hh_user_id=new_hh_uid,
            requested_account_id=hh_linked_account_id,
        )

    other = await repo.get_by_user_and_hh_user_id(user_id, new_hh_uid)
    if other is not None and other.id != hh_linked_account_id:
        other = await repo.update(
            other,
            browser_storage_enc=enc_storage,
            browser_storage_updated_at=now,
            revoked_at=None,
            last_used_at=now,
        )
        await repo.clear_resume_list_cache(other)
        return BrowserStoragePersistResult(
            outcome=BrowserStoragePersistOutcome.UPDATED_OTHER_EXISTING,
            account_id=other.id,
            hh_user_id=new_hh_uid,
            requested_account_id=hh_linked_account_id,
        )

    kwargs: dict[str, Any] = {
        "browser_storage_enc": enc_storage,
        "browser_storage_updated_at": now,
        "revoked_at": None,
        "last_used_at": now,
        "hh_user_id": new_hh_uid,
    }
    acc = await repo.update(acc, **kwargs)
    await repo.clear_resume_list_cache(acc)
    return BrowserStoragePersistResult(
        outcome=BrowserStoragePersistOutcome.UPDATED_TARGET_IDENTITY,
        account_id=acc.id,
        hh_user_id=new_hh_uid,
        requested_account_id=hh_linked_account_id,
    )
