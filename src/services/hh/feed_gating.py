"""Resolve how a feed session should bind to HeadHunter linked accounts."""

from __future__ import annotations

from enum import Enum
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.hh_linked_account import HhLinkedAccount
from src.repositories.hh_linked_account import HhLinkedAccountRepository

_BROWSER_ONLY_PLACEHOLDER_EXPIRES_AT = datetime(2100, 1, 1, 0, 0, 0)


class HhFeedAccountStatus(Enum):
    NONE = "none"
    SINGLE = "single"
    MULTI = "multi"


class HhFeedAccountCapability(str, Enum):
    API = "api"
    BROWSER = "browser"


def default_feed_account_capability() -> HhFeedAccountCapability:
    from src.config import settings

    return (
        HhFeedAccountCapability.BROWSER
        if settings.hh_ui_apply_enabled
        else HhFeedAccountCapability.API
    )


def hh_account_supports_browser(account: HhLinkedAccount) -> bool:
    return bool(account.browser_storage_enc)


def hh_account_supports_api(account: HhLinkedAccount) -> bool:
    return account.access_expires_at != _BROWSER_ONLY_PLACEHOLDER_EXPIRES_AT


def hh_account_supports_capability(
    account: HhLinkedAccount,
    capability: HhFeedAccountCapability,
) -> bool:
    if capability == HhFeedAccountCapability.BROWSER:
        return hh_account_supports_browser(account)
    return hh_account_supports_api(account)


def filter_hh_accounts_for_capability(
    accounts: list[HhLinkedAccount],
    capability: HhFeedAccountCapability,
) -> list[HhLinkedAccount]:
    return [
        account
        for account in accounts
        if hh_account_supports_capability(account, capability)
    ]


async def classify_user_hh_accounts(
    session: AsyncSession,
    user_id: int,
    *,
    capability: HhFeedAccountCapability | None = None,
) -> tuple[HhFeedAccountStatus, list[HhLinkedAccount]]:
    repo = HhLinkedAccountRepository(session)
    capability = capability or default_feed_account_capability()
    accs = filter_hh_accounts_for_capability(
        list(await repo.list_active_for_user(user_id)),
        capability,
    )
    if not accs:
        return HhFeedAccountStatus.NONE, []
    if len(accs) == 1:
        return HhFeedAccountStatus.SINGLE, accs
    return HhFeedAccountStatus.MULTI, accs
