"""Tests for HH resume AI selection (autorespond)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.ai.resume_selection import (
    fallback_resume_id,
    normalize_hh_resume_cache_items,
    parse_resume_id_from_llm,
    resolve_resume_id_for_autorespond_vacancy,
)


def test_normalize_hh_resume_cache_items_empty() -> None:
    assert normalize_hh_resume_cache_items(None) == []
    assert normalize_hh_resume_cache_items([]) == []


def test_normalize_hh_resume_cache_items_keeps_id_title() -> None:
    raw = [{"id": "rid1", "title": "Backend"}, {"id": "rid2", "name": "Other"}]
    out = normalize_hh_resume_cache_items(raw)
    assert len(out) == 2
    assert out[0] == {"id": "rid1", "title": "Backend"}
    assert out[1]["id"] == "rid2"
    assert out[1]["title"] == "Other"


def test_parse_resume_id_from_llm_plain_json() -> None:
    assert parse_resume_id_from_llm('{"resume_id":"abc123"}', {"abc123"}) == "abc123"


def test_parse_resume_id_from_llm_fenced() -> None:
    text = '```json\n{"resume_id":"x1"}\n```'
    assert parse_resume_id_from_llm(text, {"x1"}) == "x1"


def test_parse_resume_id_from_llm_rejects_unknown() -> None:
    assert parse_resume_id_from_llm('{"resume_id":"nope"}', {"a", "b"}) is None


def test_fallback_resume_id_prefers_stored_when_valid() -> None:
    items = [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}]
    assert fallback_resume_id(items, "b") == "b"
    assert fallback_resume_id(items, None) == "a"
    assert fallback_resume_id(items, "zzz") == "a"


@pytest.mark.asyncio
async def test_resolve_single_resume_skips_llm() -> None:
    vac = SimpleNamespace(id=1, title="Dev", description="desc")
    items = [{"id": "only", "title": "One"}]
    client = MagicMock()
    client.generate_text = AsyncMock()
    rid = await resolve_resume_id_for_autorespond_vacancy(
        client,
        vac,
        items,
        stored_autorespond_resume_id=None,
    )
    assert rid == "only"
    client.generate_text.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_multi_resume_calls_llm() -> None:
    vac = SimpleNamespace(id=1, title="Python Dev", description="django")
    items = [{"id": "a", "title": "Py"}, {"id": "b", "title": "Java"}]
    client = MagicMock()
    client.generate_text = AsyncMock(return_value='{"resume_id":"a"}')
    rid = await resolve_resume_id_for_autorespond_vacancy(
        client,
        vac,
        items,
        stored_autorespond_resume_id="b",
    )
    assert rid == "a"
    client.generate_text.assert_called_once()
