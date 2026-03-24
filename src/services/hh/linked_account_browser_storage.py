"""Persist encrypted Playwright storage_state into hh_linked_accounts (OAuth + browser UI)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.hh_linked_account import HhLinkedAccountRepository
from src.services.hh.crypto import HhTokenCipher
from src.services.hh_ui.browser_link import (
    encrypt_storage_for_account,
    make_hh_user_id_for_browser_link,
    placeholder_access_expires_at,
    placeholder_token_ciphertexts,
)


def utc_naive_now() -> datetime:
    from datetime import UTC

    return datetime.now(UTC).replace(tzinfo=None)


async def persist_browser_storage_state_for_user(
    db_session: AsyncSession,
    user_id: int,
    state_dict: dict,
    *,
    cipher: HhTokenCipher,
) -> None:
    """Create or update a linked row with browser storage; reactivates revoked rows."""
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
    await repo.clear_resume_list_cache(acc)
