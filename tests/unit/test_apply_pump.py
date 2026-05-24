"""Apply pump: pop batch, read cached letters, run Playwright, tick bar, chain self."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.hh_ui.outcomes import ApplyOutcome, ApplyResult
from src.services.hh_ui.runner import VacancyApplySpec


@pytest.fixture(autouse=True)
def _stub_cryptography(monkeypatch: pytest.MonkeyPatch):
    crypto = ModuleType("cryptography")
    fernet = ModuleType("cryptography.fernet")
    fernet.Fernet = MagicMock()
    fernet.InvalidToken = Exception
    monkeypatch.setitem(sys.modules, "cryptography", crypto)
    monkeypatch.setitem(sys.modules, "cryptography.fernet", fernet)


def _spec(vid: int, hh_id: str = "100") -> dict:
    return {
        "autoparsed_vacancy_id": vid,
        "hh_vacancy_id": hh_id,
        "resume_id": "r1",
        "vacancy_url": f"https://hh.ru/vacancy/{hh_id}",
    }


def _build_async_pump_async(monkeypatch: pytest.MonkeyPatch):
    """Apply common patches used by every pump test."""
    bot = MagicMock()
    bot.session.close = AsyncMock()
    self = MagicMock()
    self.create_bot.return_value = bot
    self.request = MagicMock()
    self.request.id = "test-pump-owner"

    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session_factory = MagicMock(return_value=session)

    acc = MagicMock()
    acc.browser_storage_enc = b"enc"
    acc_repo = MagicMock()
    acc_repo.get_by_id = AsyncMock(return_value=acc)

    settings_repo = MagicMock()
    settings_repo.get_value = AsyncMock(return_value=False)

    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply.HhLinkedAccountRepository",
        lambda *a, **k: acc_repo,
    )
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply.AppSettingRepository",
        lambda *a, **k: settings_repo,
    )
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply.HhTokenCipher",
        lambda *a, **k: MagicMock(),
    )
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply.decrypt_browser_storage",
        lambda *a, **k: {"cookies": []},
    )

    guard = MagicMock()
    guard.wait_if_overloaded = AsyncMock()
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply.get_system_load_guard",
        lambda: guard,
    )
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply.try_acquire_pump_lock",
        lambda *a, **k: True,
    )
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply.release_pump_lock",
        MagicMock(),
    )
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply.renew_pump_lock",
        lambda *a, **k: True,
    )
    monkeypatch.setattr(
        "src.services.autorespond_progress.is_autorespond_cancelled_sync",
        lambda *a, **k: False,
    )
    monkeypatch.setattr(
        "src.services.progress_cancel.is_user_cancelled_sync",
        lambda *a, **k: False,
    )
    monkeypatch.setattr(
        "src.services.autorespond_progress.ensure_autorespond_progress_task_state_if_missing",
        AsyncMock(),
    )
    return self, session_factory, bot


def _envelope() -> dict:
    return {
        "user_id": 7,
        "chat_id": 42,
        "message_id": 0,
        "locale": "ru",
        "hh_linked_account_id": 5,
        "feed_session_id": 0,
        "cover_letter_style": "professional",
        "cover_task_enabled": True,
        "silent_feed": True,
        "autorespond_progress": {
            "task_key": "autorespond:1:abc",
            "total": 2,
            "locale": "ru",
        },
    }


@pytest.mark.asyncio
async def test_apply_pump_exits_when_ready_set_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    self, session_factory, bot = _build_async_pump_async(monkeypatch)

    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply.pop_ready_batch",
        lambda *a, **k: [],
    )
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply.ready_remaining_count",
        lambda *a, **k: 0,
    )
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply.pregen_pending_count",
        lambda *a, **k: 0,
    )
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply.touch_pump_heartbeat",
        MagicMock(),
    )

    from src.worker.tasks.hh_ui_apply import _apply_pump_async

    result = await _apply_pump_async(self, session_factory, "autorespond:1:abc", 42, _envelope())
    assert result == {"status": "ok", "processed": 0, "abort": None}


@pytest.mark.asyncio
async def test_apply_pump_processes_batch_and_ticks_bar(monkeypatch: pytest.MonkeyPatch) -> None:
    self, session_factory, bot = _build_async_pump_async(monkeypatch)

    pops = [
        [_spec(101), _spec(102, "200")],
        [],
    ]

    def _pop(*_args, **_kwargs):
        return pops.pop(0) if pops else []

    monkeypatch.setattr("src.worker.tasks.hh_ui_apply.pop_ready_batch", _pop)
    monkeypatch.setattr("src.worker.tasks.hh_ui_apply.ready_remaining_count", lambda *a, **k: 0)
    monkeypatch.setattr("src.worker.tasks.hh_ui_apply.pregen_pending_count", lambda *a, **k: 0)
    monkeypatch.setattr("src.worker.tasks.hh_ui_apply.touch_pump_heartbeat", MagicMock())

    fetched: list[int] = []

    def _fetch(_chat, _task, vid):
        fetched.append(vid)
        return "cached letter"

    monkeypatch.setattr("src.worker.tasks.hh_ui_apply.fetch_pregen_letter", _fetch)
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply._resolve_cover_letter_for_apply",
        AsyncMock(side_effect=lambda _sf, _chat, _key, vid: _fetch(_chat, _key, vid) or ""),
    )

    received_specs: list[VacancyApplySpec] = []

    def _fake_batch(*, storage_state, items, on_item_done, **_kwargs):
        for spec in items:
            received_specs.append(spec)
            on_item_done(spec, ApplyResult(outcome=ApplyOutcome.SUCCESS))
        return [], None

    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply.apply_to_vacancies_ui_batch",
        _fake_batch,
    )
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply._finalize_pump_item_async",
        AsyncMock(),
    )

    with patch("src.worker.tasks.hh_ui_apply.settings") as mock_settings:
        mock_settings.hh_token_encryption_key = "secret"
        mock_settings.hh_ui_apply_batch_size = 4
        mock_settings.autorespond_apply_pump_soft_time_limit = 60
        mock_settings.autorespond_apply_pump_chain_grace_seconds = 5
        mock_settings.autorespond_apply_pump_pregen_wait_per_item_seconds = 0.0
        mock_settings.hh_ui_apply_max_retries = 1
        mock_settings.hh_ui_apply_retry_initial_seconds = 1.0
        mock_settings.hh_ui_apply_retry_delay_cap_seconds = 1.0
        mock_settings.hh_ui_debug_screenshot_dir = "/tmp"

        from src.worker.tasks.hh_ui_apply import _apply_pump_async

        result = await _apply_pump_async(
            self, session_factory, "autorespond:1:abc", 42, _envelope()
        )

    assert result["status"] == "ok"
    assert result["processed"] == 2
    assert {s.autoparsed_vacancy_id for s in received_specs} == {101, 102}
    assert all(s.cover_letter == "cached letter" for s in received_specs)
    assert fetched == [101, 102]


@pytest.mark.asyncio
async def test_apply_pump_chains_self_when_ready_remaining(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the shift exits with work still queued, the pump must re-enqueue itself."""
    self, session_factory, bot = _build_async_pump_async(monkeypatch)

    monkeypatch.setattr("src.worker.tasks.hh_ui_apply.pop_ready_batch", lambda *a, **k: [])
    monkeypatch.setattr("src.worker.tasks.hh_ui_apply.pregen_pending_count", lambda *a, **k: 0)
    monkeypatch.setattr("src.worker.tasks.hh_ui_apply.touch_pump_heartbeat", MagicMock())
    # After the inner loop exits (no batch, no pending pregens), the chain check sees
    # leftover work in the ZSET and re-enqueues the pump for the next shift.
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply.ready_remaining_count",
        lambda *a, **k: 7,
    )

    delay_mock = MagicMock()
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply.apply_pump_task",
        MagicMock(delay=delay_mock),
    )

    from src.worker.tasks.hh_ui_apply import _apply_pump_async

    result = await _apply_pump_async(self, session_factory, "autorespond:1:abc", 42, _envelope())
    assert result["abort"] is None
    delay_mock.assert_called_once()


@pytest.mark.asyncio
async def test_apply_pump_aborts_on_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    self, session_factory, bot = _build_async_pump_async(monkeypatch)

    cancelled = {"count": 0}

    def _cancel_check(*_a, **_k):
        cancelled["count"] += 1
        return cancelled["count"] >= 1

    monkeypatch.setattr(
        "src.services.autorespond_progress.is_autorespond_cancelled_sync",
        _cancel_check,
    )
    monkeypatch.setattr("src.worker.tasks.hh_ui_apply.pop_ready_batch", lambda *a, **k: [])
    monkeypatch.setattr("src.worker.tasks.hh_ui_apply.ready_remaining_count", lambda *a, **k: 5)
    monkeypatch.setattr("src.worker.tasks.hh_ui_apply.pregen_pending_count", lambda *a, **k: 0)
    monkeypatch.setattr("src.worker.tasks.hh_ui_apply.touch_pump_heartbeat", MagicMock())

    delay_mock = MagicMock()
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply.apply_pump_task",
        MagicMock(delay=delay_mock),
    )

    from src.worker.tasks.hh_ui_apply import _apply_pump_async

    result = await _apply_pump_async(self, session_factory, "autorespond:1:abc", 42, _envelope())
    assert result["abort"] == "cancelled"
    delay_mock.assert_not_called()


@pytest.mark.asyncio
async def test_apply_pump_skips_when_lock_not_acquired(monkeypatch: pytest.MonkeyPatch) -> None:
    self, session_factory, _bot = _build_async_pump_async(monkeypatch)
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply.try_acquire_pump_lock",
        lambda *a, **k: False,
    )

    from src.worker.tasks.hh_ui_apply import _apply_pump_async

    result = await _apply_pump_async(self, session_factory, "autorespond:1:abc", 42, _envelope())
    assert result == {"status": "skipped", "processed": 0, "abort": "pump_lock_held"}


@pytest.mark.asyncio
async def test_apply_pump_defers_missing_cover_letter_without_failed_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing letter waits for pregen or reschedules it; no failed counter / bar tick."""
    self, session_factory, bot = _build_async_pump_async(monkeypatch)

    spec = _spec(101)
    pops = [[spec], []]

    def _pop(*_args, **_kwargs):
        return pops.pop(0) if pops else []

    monkeypatch.setattr("src.worker.tasks.hh_ui_apply.pop_ready_batch", _pop)
    monkeypatch.setattr("src.worker.tasks.hh_ui_apply.ready_remaining_count", lambda *a, **k: 0)
    monkeypatch.setattr("src.worker.tasks.hh_ui_apply.pregen_pending_count", lambda *a, **k: 0)
    monkeypatch.setattr("src.worker.tasks.hh_ui_apply.touch_pump_heartbeat", MagicMock())
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply._resolve_cover_letter_for_apply",
        AsyncMock(return_value=""),
    )
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply.is_pregen_pending_for_vacancy",
        lambda *a, **k: False,
    )

    schedule_mock = MagicMock()
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply._schedule_pregen_for_apply_spec",
        schedule_mock,
    )
    finalize_mock = AsyncMock()
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply._finalize_pump_item_async",
        finalize_mock,
    )
    failed_mock = MagicMock()
    monkeypatch.setattr(
        "src.services.autorespond_progress.increment_autorespond_failed_sync",
        failed_mock,
    )
    batch_mock = MagicMock()
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply.apply_to_vacancies_ui_batch",
        batch_mock,
    )

    sleep_calls: list[float] = []

    async def _fast_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr("src.worker.tasks.hh_ui_apply.asyncio.sleep", _fast_sleep)

    from src.worker.tasks.hh_ui_apply import _apply_pump_async

    result = await _apply_pump_async(
        self, session_factory, "autorespond:1:abc", 42, _envelope()
    )

    assert result["processed"] == 0
    schedule_mock.assert_called_once()
    finalize_mock.assert_not_awaited()
    failed_mock.assert_not_called()
    batch_mock.assert_not_called()
    assert sleep_calls == [0.5]


@pytest.mark.asyncio
async def test_apply_pump_waits_when_pregen_pending_for_missing_letter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    self, session_factory, _bot = _build_async_pump_async(monkeypatch)

    pops = [[_spec(101)], []]

    def _pop(*_args, **_kwargs):
        return pops.pop(0) if pops else []

    monkeypatch.setattr("src.worker.tasks.hh_ui_apply.pop_ready_batch", _pop)
    monkeypatch.setattr("src.worker.tasks.hh_ui_apply.ready_remaining_count", lambda *a, **k: 0)
    pending_checks = {"n": 0}

    def _pending_count(*_a, **_k):
        pending_checks["n"] += 1
        return 1 if pending_checks["n"] == 1 else 0

    monkeypatch.setattr("src.worker.tasks.hh_ui_apply.pregen_pending_count", _pending_count)
    monkeypatch.setattr("src.worker.tasks.hh_ui_apply.touch_pump_heartbeat", MagicMock())
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply._resolve_cover_letter_for_apply",
        AsyncMock(return_value=""),
    )
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply.is_pregen_pending_for_vacancy",
        lambda *a, **k: True,
    )

    schedule_mock = MagicMock()
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply._schedule_pregen_for_apply_spec",
        schedule_mock,
    )

    from src.worker.tasks.hh_ui_apply import _apply_pump_async

    await _apply_pump_async(self, session_factory, "autorespond:1:abc", 42, _envelope())

    schedule_mock.assert_not_called()


@pytest.mark.asyncio
async def test_apply_pump_does_not_chain_when_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    self, session_factory, _bot = _build_async_pump_async(monkeypatch)

    monkeypatch.setattr("src.worker.tasks.hh_ui_apply.pop_ready_batch", lambda *a, **k: [])
    monkeypatch.setattr("src.worker.tasks.hh_ui_apply.pregen_pending_count", lambda *a, **k: 0)
    monkeypatch.setattr("src.worker.tasks.hh_ui_apply.touch_pump_heartbeat", MagicMock())
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply.ready_remaining_count",
        lambda *a, **k: 7,
    )
    monkeypatch.setattr(
        "src.services.autorespond_progress.is_autorespond_cancelled_sync",
        lambda *a, **k: True,
    )

    delay_mock = MagicMock()
    monkeypatch.setattr(
        "src.worker.tasks.hh_ui_apply.apply_pump_task",
        MagicMock(delay=delay_mock),
    )

    from src.worker.tasks.hh_ui_apply import _apply_pump_async

    result = await _apply_pump_async(self, session_factory, "autorespond:1:abc", 42, _envelope())
    assert result["abort"] == "cancelled"
    delay_mock.assert_not_called()
