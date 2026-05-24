"""Cover-letter pre-generation task: DB persist, enqueue apply, failure handling."""

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
def fake_pregen_state(monkeypatch: pytest.MonkeyPatch) -> dict[tuple[int, str, int], str]:
    """Track ``store_pregen_letter`` writes + ``fetch_pregen_letter`` lookups."""
    store: dict[tuple[int, str, int], str] = {}

    def _store(chat_id: int, task_key: str, vacancy_id: int, letter: str) -> None:
        store[(chat_id, task_key, vacancy_id)] = letter

    def _fetch(chat_id: int, task_key: str, vacancy_id: int) -> str | None:
        key = (chat_id, task_key, vacancy_id)
        return store.get(key)

    def _exists(chat_id: int, task_key: str, vacancy_id: int) -> bool:
        return (chat_id, task_key, vacancy_id) in store

    monkeypatch.setattr(
        "src.services.autorespond_pipeline_state.store_pregen_letter",
        _store,
    )
    monkeypatch.setattr(
        "src.services.autorespond_pipeline_state.fetch_pregen_letter",
        _fetch,
    )
    monkeypatch.setattr(
        "src.services.autorespond_pipeline_state.pregen_letter_exists",
        _exists,
    )
    monkeypatch.setattr(
        "src.services.autorespond_pipeline_state.release_pregen_pending",
        MagicMock(),
    )
    return store


_APPLY_SPEC = {
    "autoparsed_vacancy_id": 99,
    "hh_vacancy_id": "100",
    "resume_id": "r1",
    "vacancy_url": "https://hh.ru/vacancy/100",
    "company_id": 1,
}


@pytest.mark.asyncio
async def test_pregenerate_writes_letter_to_cache_and_enqueues_apply(
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
    monkeypatch.setattr(
        "src.worker.tasks.cover_letter._persist_autorespond_cover_letter",
        AsyncMock(),
    )
    enqueue_mock = MagicMock()
    monkeypatch.setattr(
        "src.services.autorespond_pipeline_state.enqueue_autorespond_apply_unit",
        enqueue_mock,
    )

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
        celery_task=None,
        task_key="autorespond:1:abc",
        chat_id=42,
        user_id=7,
        autoparsed_vacancy_id=99,
        resume_id="r1",
        cover_letter_style="professional",
        apply_spec=_APPLY_SPEC,
    )

    assert result["status"] == "ok"
    assert fake_pregen_state[(42, "autorespond:1:abc", 99)] == "Hello hiring manager."
    enqueue_mock.assert_called_once_with(42, "autorespond:1:abc", _APPLY_SPEC)


@pytest.mark.asyncio
async def test_pregenerate_timeout_does_not_enqueue_apply(
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
    enqueue_mock = MagicMock()
    monkeypatch.setattr(
        "src.services.autorespond_pipeline_state.enqueue_autorespond_apply_unit",
        enqueue_mock,
    )
    monkeypatch.setattr(
        "src.worker.tasks.cover_letter._report_autorespond_pregen_failure",
        AsyncMock(),
    )

    with patch("src.worker.tasks.cover_letter.settings") as mock_settings:
        mock_settings.cover_letter_pregen_soft_time_limit = 0.05
        from src.worker.tasks.cover_letter import _pregenerate_for_apply_async

        result = await _pregenerate_for_apply_async(
            session_factory=MagicMock(),
            celery_task=None,
            task_key="autorespond:1:abc",
            chat_id=42,
            user_id=7,
            autoparsed_vacancy_id=99,
            resume_id="r1",
            cover_letter_style="professional",
            apply_spec=_APPLY_SPEC,
        )

    assert result["status"] == "timeout"
    assert (42, "autorespond:1:abc", 99) not in fake_pregen_state
    enqueue_mock.assert_not_called()


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
    enqueue_mock = MagicMock()
    monkeypatch.setattr(
        "src.services.autorespond_pipeline_state.enqueue_autorespond_apply_unit",
        enqueue_mock,
    )

    from src.worker.tasks.cover_letter import _pregenerate_for_apply_async

    result = await _pregenerate_for_apply_async(
        session_factory=MagicMock(),
        celery_task=None,
        task_key="autorespond:1:abc",
        chat_id=42,
        user_id=7,
        autoparsed_vacancy_id=99,
        resume_id="r1",
        cover_letter_style="professional",
        apply_spec=_APPLY_SPEC,
    )
    assert result["status"] == "cached"
    sentinel.assert_not_called()
    enqueue_mock.assert_called_once()


@pytest.mark.asyncio
async def test_pregenerate_cancels_when_autorespond_cancelled(
    fake_pregen_state: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.services.autorespond_progress.is_autorespond_cancelled_sync",
        lambda *a, **k: True,
    )
    enqueue_mock = MagicMock()
    monkeypatch.setattr(
        "src.services.autorespond_pipeline_state.enqueue_autorespond_apply_unit",
        enqueue_mock,
    )

    from src.worker.tasks.cover_letter import _pregenerate_for_apply_async

    result = await _pregenerate_for_apply_async(
        session_factory=MagicMock(),
        celery_task=None,
        task_key="autorespond:1:abc",
        chat_id=42,
        user_id=7,
        autoparsed_vacancy_id=99,
        resume_id="r1",
        cover_letter_style="professional",
        apply_spec=_APPLY_SPEC,
    )
    assert result["status"] == "cancelled"
    assert (42, "autorespond:1:abc", 99) not in fake_pregen_state
    enqueue_mock.assert_not_called()
