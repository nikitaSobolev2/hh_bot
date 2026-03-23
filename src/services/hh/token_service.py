"""Resolve a valid access token for a linked HH account (refresh when needed)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.hh_linked_account import HhLinkedAccount
from src.repositories.hh_linked_account import HhLinkedAccountRepository
from src.services.hh.crypto import HhTokenCipher
from src.services.hh.oauth_tokens import refresh_tokens


def _utc_naive_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _needs_refresh(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return True
    return _utc_naive_now() >= expires_at - timedelta(seconds=90)


def get_cipher() -> HhTokenCipher:
    return HhTokenCipher(settings.hh_token_encryption_key)


async def ensure_access_token(
    session: AsyncSession,
    account_id: int,
) -> tuple[HhLinkedAccount, str]:
    repo = HhLinkedAccountRepository(session)
    account = await repo.get_by_id(account_id)
    if not account or account.revoked_at:
        raise ValueError("Linked HeadHunter account not found or revoked")
    cipher = get_cipher()
    access = cipher.decrypt_to_str(account.access_token_enc)
    now = _utc_naive_now()

    if _needs_refresh(account.access_expires_at):
        refresh_plain = cipher.decrypt_to_str(account.refresh_token_enc)
        data = await refresh_tokens(refresh_token=refresh_plain)
        access = data["access_token"]
        refresh_new = data["refresh_token"]
        expires_in = int(data.get("expires_in", 3600))
        await repo.update(
            account,
            access_token_enc=cipher.encrypt(access),
            refresh_token_enc=cipher.encrypt(refresh_new),
            access_expires_at=now + timedelta(seconds=max(120, expires_in - 120)),
            last_used_at=now,
        )
    else:
        await repo.update(account, last_used_at=now)
    await session.flush()
    return account, access
