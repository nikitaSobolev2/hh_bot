"""Tests for HeadHunter feed account capability gating."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.hh.feed_gating import (
    HhFeedAccountCapability,
    HhFeedAccountStatus,
    classify_user_hh_accounts,
    filter_hh_accounts_for_capability,
)


def test_filter_hh_accounts_for_browser_capability() -> None:
    browser_only = SimpleNamespace(browser_storage_enc=b"x", access_expires_at=datetime(2100, 1, 1))
    api_only = SimpleNamespace(browser_storage_enc=None, access_expires_at=datetime(2026, 1, 1))

    filtered = filter_hh_accounts_for_capability(
        [browser_only, api_only],
        HhFeedAccountCapability.BROWSER,
    )

    assert filtered == [browser_only]


def test_filter_hh_accounts_for_api_capability_excludes_browser_placeholder_rows() -> None:
    browser_only = SimpleNamespace(browser_storage_enc=b"x", access_expires_at=datetime(2100, 1, 1))
    api_only = SimpleNamespace(browser_storage_enc=None, access_expires_at=datetime(2026, 1, 1))

    filtered = filter_hh_accounts_for_capability(
        [browser_only, api_only],
        HhFeedAccountCapability.API,
    )

    assert filtered == [api_only]


async def _classify(capability: HhFeedAccountCapability):
    session = MagicMock()
    accounts = [
        SimpleNamespace(id=1, browser_storage_enc=b"x", access_expires_at=datetime(2100, 1, 1)),
        SimpleNamespace(id=2, browser_storage_enc=None, access_expires_at=datetime(2026, 1, 1)),
    ]
    repo = MagicMock()
    repo.list_active_for_user = AsyncMock(return_value=accounts)
    with patch(
        "src.services.hh.feed_gating.HhLinkedAccountRepository",
        return_value=repo,
    ):
        return await classify_user_hh_accounts(session, 7, capability=capability)


@pytest.mark.asyncio
async def test_classify_user_hh_accounts_filters_by_browser_capability() -> None:
    status, accounts = await _classify(HhFeedAccountCapability.BROWSER)
    assert status == HhFeedAccountStatus.SINGLE
    assert [acc.id for acc in accounts] == [1]


@pytest.mark.asyncio
async def test_classify_user_hh_accounts_filters_by_api_capability() -> None:
    status, accounts = await _classify(HhFeedAccountCapability.API)
    assert status == HhFeedAccountStatus.SINGLE
    assert [acc.id for acc in accounts] == [2]
