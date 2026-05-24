"""Cover-letter pre-generation task: cache write, timeout fallback, idempotency."""

from __future__ import annotations

import asyncio
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _stub_cryptography(monkeypatch: pytest.MonkeyPatch):
    """Avoid importing real cryptography (decoupled from this layer)."""
    cryptography_mod = ModuleType("cryptography")
    fernet_mod = ModuleType("cryptography.fernet")
    fernet_mod.Fernet = MagicMock()
    fernet_mod.InvalidToken = Exception
    monkeypatch.setitem(sys.modules, "cryptography", cryptography_mod)
    monkeypatch.setitem(sys.modules, "cryptography.fernet", fernet_mod)


@pytest.fixture
def fake_pregen_state(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Track ``store_pregen_letter`` writes + ``pregen_letter_exists`` lookups."""
    store: dict[tuple[int, str, int], str] = {}

    def _store(chat_id: int, task_key: str, vacancy_id: int, letter: str) -> None:
        store[(chat_id, task_key, vacancy_id)] = letter

    def _exists(chat_id: int, task_key: str, vacancy_id: int) -> bool:
        return (chat_id, task_key, vacancy_id) in store

    monkeypatch.setattr(
        "src.worker.tasks.cover_letter.store_pregen_letter",
        _store,
        raising=False,
    )
    # Patch the pipeline-state module for in-function import.
    monkeypatch.setattr(
        "src.services.autorespond_pipeline_state.store_pregen_letter",
        _store,
    )
    monkeypatch.setattr(
        "src.services.autorespond_pipeline_state.pregen_letter_exists",
        _exists,
    )
    return store


@pytest.mark.asyncio
async def test_pregenerate_writes_letter_to_cache_on_success(
    fake_pregen_state: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_generate(*_args, **_kwargs) -> str:
        return "Hello hiring manager."

    monkeypatch.setattr(
        "src.worker.tasks.cover_letter.generate_cover_letter_plaintext_for_autoparsed_vacancy",
        fake_generate,
    )
    monkeypatch.setattr("src.services.ai.client.AIClient", MagicMock())
    monkeypatch.setattr("src.services.ai.client.close_ai_client", AsyncMock())

    guard = MagicMock()
    guard.wait_if_overloaded = AsyncMock()
    monkeypatch.setattr(
        "src.core.system_load.get_system_load_guard",
        lambda: guard,
    )
    monkeypatch.setattr(
        "src.services.autorespond_progress.is_autorespond_cancelled_sync",
        lambda *a, **k: False,
    )

    from src.worker.tasks.cover_letter import _pregenerate_for_apply_async

    result = await _pregenerate_for_apply_async(
        session_factory=MagicMock(),
        task_key="autorespond:1:abc",
        chat_id=42,
        user_id=7,
        autoparsed_vacancy_id=99,
        resume_id="r1",
        cover_letter_style="professional",
    )

    assert result["status"] == "ok"
    assert fake_pregen_state[(42, "autorespond:1:abc", 99)] == "Hello hiring manager."


@pytest.mark.asyncio
async def test_pregenerate_timeout_writes_empty_letter(
    fake_pregen_state: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def slow_generate(*_args, **_kwargs) -> str:
        await asyncio.sleep(10)
        return "never"

    monkeypatch.setattr(
        "src.worker.tasks.cover_letter.generate_cover_letter_plaintext_for_autoparsed_vacancy",
        slow_generate,
    )
    monkeypatch.setattr("src.services.ai.client.AIClient", MagicMock())
    monkeypatch.setattr("src.services.ai.client.close_ai_client", AsyncMock())
    guard = MagicMock()
    guard.wait_if_overloaded = AsyncMock()
    monkeypatch.setattr(
        "src.core.system_load.get_system_load_guard",
        lambda: guard,
    )
    monkeypatch.setattr(
        "src.services.autorespond_progress.is_autorespond_cancelled_sync",
        lambda *a, **k: False,
    )

    with patch("src.worker.tasks.cover_letter.settings") as mock_settings:
        mock_settings.cover_letter_pregen_soft_time_limit = 0.05
        from src.worker.tasks.cover_letter import _pregenerate_for_apply_async

        result = await _pregenerate_for_apply_async(
            session_factory=MagicMock(),
            task_key="autorespond:1:abc",
            chat_id=42,
            user_id=7,
            autoparsed_vacancy_id=99,
            resume_id="r1",
            cover_letter_style="professional",
        )

    assert result["status"] == "timeout"
    assert fake_pregen_state[(42, "autorespond:1:abc", 99)] == ""


@pytest.mark.asyncio
async def test_pregenerate_is_idempotent_when_letter_already_cached(
    fake_pregen_state: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pregen_state[(42, "autorespond:1:abc", 99)] = "cached"

    sentinel = MagicMock(side_effect=AssertionError("should not be called"))
    monkeypatch.setattr(
        "src.worker.tasks.cover_letter.generate_cover_letter_plaintext_for_autoparsed_vacancy",
        sentinel,
    )

    from src.worker.tasks.cover_letter import _pregenerate_for_apply_async

    result = await _pregenerate_for_apply_async(
        session_factory=MagicMock(),
        task_key="autorespond:1:abc",
        chat_id=42,
        user_id=7,
        autoparsed_vacancy_id=99,
        resume_id="r1",
        cover_letter_style="professional",
    )
    assert result["status"] == "cached"
    sentinel.assert_not_called()


@pytest.mark.asyncio
async def test_pregenerate_cancels_when_autorespond_cancelled(
    fake_pregen_state: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.services.autorespond_progress.is_autorespond_cancelled_sync",
        lambda *a, **k: True,
    )

    from src.worker.tasks.cover_letter import _pregenerate_for_apply_async

    result = await _pregenerate_for_apply_async(
        session_factory=MagicMock(),
        task_key="autorespond:1:abc",
        chat_id=42,
        user_id=7,
        autoparsed_vacancy_id=99,
        resume_id="r1",
        cover_letter_style="professional",
    )
    assert result["status"] == "cancelled"
    assert fake_pregen_state[(42, "autorespond:1:abc", 99)] == ""
