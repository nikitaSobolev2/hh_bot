"""Tests for HH linked account resume list cache helpers."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.modules.autoparse.feed_handlers import _resume_cache_to_lists
from src.repositories.hh_linked_account import HhLinkedAccountRepository


@pytest.mark.asyncio
async def test_clear_resume_list_cache_updates_entity() -> None:
    session = MagicMock()
    session.flush = AsyncMock()
    acc = MagicMock()
    repo = HhLinkedAccountRepository(session)
    repo.update = AsyncMock(return_value=acc)

    out = await repo.clear_resume_list_cache(acc)

    assert out is acc
    repo.update.assert_called_once()
    kwargs = repo.update.call_args[1]
    assert kwargs["resume_list_cache"] is None
    assert kwargs["resume_list_cached_at"] is None


@pytest.mark.asyncio
async def test_update_resume_list_cache_sets_json_and_timestamp() -> None:
    session = MagicMock()
    session.flush = AsyncMock()
    acc = MagicMock()
    repo = HhLinkedAccountRepository(session)
    repo.update = AsyncMock(return_value=acc)
    items = [{"id": "r1", "title": "Developer"}]

    out = await repo.update_resume_list_cache(acc, items)

    assert out is acc
    kwargs = repo.update.call_args[1]
    assert kwargs["resume_list_cache"] == items
    assert kwargs["resume_list_cached_at"] is not None


def test_resume_cache_to_lists_valid() -> None:
    got = _resume_cache_to_lists([{"id": "abc", "title": "My CV"}])
    assert got == (["abc"], ["My CV"])


def test_resume_cache_to_lists_missing_title_uses_id() -> None:
    got = _resume_cache_to_lists([{"id": "x"}])
    assert got == (["x"], ["x"])


def test_resume_cache_to_lists_rejects_empty() -> None:
    assert _resume_cache_to_lists([]) is None
    assert _resume_cache_to_lists(None) is None
    assert _resume_cache_to_lists([{"title": "no id"}]) is None
