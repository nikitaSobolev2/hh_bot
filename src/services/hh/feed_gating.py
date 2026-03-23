"""Resolve how a feed session should bind to HeadHunter linked accounts."""

from __future__ import annotations

from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.hh_linked_account import HhLinkedAccount
from src.repositories.hh_linked_account import HhLinkedAccountRepository


class HhFeedAccountStatus(Enum):
    NONE = "none"
    SINGLE = "single"
    MULTI = "multi"


async def classify_user_hh_accounts(
    session: AsyncSession,
    user_id: int,
) -> tuple[HhFeedAccountStatus, list[HhLinkedAccount]]:
    repo = HhLinkedAccountRepository(session)
    accs = await repo.list_active_for_user(user_id)
    if not accs:
        return HhFeedAccountStatus.NONE, []
    if len(accs) == 1:
        return HhFeedAccountStatus.SINGLE, accs
    return HhFeedAccountStatus.MULTI, accs
