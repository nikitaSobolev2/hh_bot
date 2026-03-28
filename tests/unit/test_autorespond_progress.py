"""Unit tests for autorespond pinned progress (work units vs pre-skips)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.modules.autoparse.autorespond_logic import work_units_for_autorespond_progress


def _vac(*, hh_id: str = "1", needs_eq: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        hh_vacancy_id=hh_id,
        needs_employer_questions=needs_eq,
    )


def test_work_units_all_pre_skipped_by_attempt_set() -> None:
    capped = [_vac(hh_id="a"), _vac(hh_id="b")]
    already = {"a", "b"}
    work, pre = work_units_for_autorespond_progress(capped, already)
    assert work == 0
    assert pre == 2


def test_work_units_none_pre_skipped() -> None:
    capped = [_vac(hh_id="1"), _vac(hh_id="2")]
    work, pre = work_units_for_autorespond_progress(capped, set())
    assert work == 2
    assert pre == 0


def test_work_units_flag_needs_employer_questions_counts_as_pre_skip() -> None:
    capped = [_vac(hh_id="x"), _vac(hh_id="y", needs_eq=True)]
    work, pre = work_units_for_autorespond_progress(capped, set())
    assert work == 1
    assert pre == 1


def test_work_units_mixed() -> None:
    capped = [
        _vac(hh_id="done1"),
        _vac(hh_id="new1"),
        _vac(hh_id="done2"),
        _vac(hh_id="new2"),
    ]
    work, pre = work_units_for_autorespond_progress(capped, {"done1", "done2"})
    assert work == 2
    assert pre == 2


def test_work_units_empty_capped() -> None:
    work, pre = work_units_for_autorespond_progress([], {"1"})
    assert work == 0
    assert pre == 0


class _FakeRedisStore:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def make_client(self, *args, **kwargs):
        store = self.store

        class _R:
            def get(self, key):
                return store.get(key)

            def set(self, key, val, ex=None):
                store[key] = val

            def delete(self, key):
                store.pop(key, None)

            def close(self) -> None:
                """No-op: in-memory fake has no connection."""

        return _R()


def test_save_checkpoint_empty_with_resume_persists_json(monkeypatch: pytest.MonkeyPatch) -> None:
    fr = _FakeRedisStore()

    def _from_url(*a, **k):
        return fr.make_client()

    monkeypatch.setattr(
        "src.services.autorespond_progress.sync_redis.Redis.from_url",
        _from_url,
    )
    from src.services.autorespond_progress import (
        hh_ui_batch_checkpoint_key,
        save_hh_ui_batch_checkpoint_sync,
    )

    save_hh_ui_batch_checkpoint_sync(7, "autorespond:1:abc", [], resume={"user_id": 99})
    key = hh_ui_batch_checkpoint_key(7, "autorespond:1:abc")
    raw = fr.store[key]
    data = json.loads(raw)
    assert data["items"] == []
    assert data["resume"] == {"user_id": 99}


def test_load_checkpoint_empty_items_returns_resume(monkeypatch: pytest.MonkeyPatch) -> None:
    fr = _FakeRedisStore()
    key = "checkpoint:hh_ui_apply_batch:7:autorespond:1:abc"
    fr.store[key] = json.dumps({"items": [], "resume": {"user_id": 42}})

    def _from_url(*a, **k):
        return fr.make_client()

    monkeypatch.setattr(
        "src.services.autorespond_progress.sync_redis.Redis.from_url",
        _from_url,
    )
    from src.services.autorespond_progress import load_hh_ui_batch_checkpoint_full_sync

    full = load_hh_ui_batch_checkpoint_full_sync(7, "autorespond:1:abc")
    assert full is not None
    items, resume = full
    assert items == []
    assert resume == {"user_id": 42}


@pytest.mark.asyncio
async def test_refresh_autorespond_merges_tail_when_child_items_empty() -> None:
    from src.bot.modules.progress.handlers import _try_refresh_autorespond

    callback = MagicMock()
    callback.answer = AsyncMock()
    i18n = MagicMock()
    i18n.get = MagicMock(return_value="ok")
    svc = MagicMock()
    svc.update_celery_task_id = AsyncMock()

    tail = [{"autoparsed_vacancy_id": 1, "hh_vacancy_id": "9", "resume_id": "r", "vacancy_url": "https://hh.ru/vacancy/9"}]
    resume = {"user_id": 1, "chat_id": 2, "message_id": 0, "locale": "ru", "hh_linked_account_id": 3, "feed_session_id": 0, "cover_letter_style": "x", "cover_task_enabled": True, "silent_feed": True, "autorespond_progress": {}}

    with (
        patch(
            "src.bot.modules.progress.handlers.is_autorespond_cancelled_sync",
            return_value=False,
        ),
        patch(
            "src.bot.modules.progress.handlers.load_hh_ui_batch_checkpoint_full_sync",
            return_value=([], resume),
        ),
        patch(
            "src.bot.modules.progress.handlers.load_autorespond_ui_tail_sync",
            return_value=tail,
        ),
        patch(
            "src.bot.modules.progress.handlers.get_hh_ui_batch_active_sync",
            return_value=None,
        ),
        patch(
            "src.bot.modules.progress.handlers.run_celery_task",
            new_callable=AsyncMock,
        ) as mock_run,
    ):
        mock_run.return_value = MagicMock(id="new-celery-id")
        await _try_refresh_autorespond(
            callback, i18n, "autorespond:8:tid", 2, svc
        )

    mock_run.assert_awaited_once()
    _args, kw = mock_run.call_args
    assert kw["items"] == tail


@pytest.mark.asyncio
async def test_refresh_autorespond_revokes_active_celery_task() -> None:
    """When a child batch is in flight, refresh terminates it before re-enqueueing."""
    from src.bot.modules.progress.handlers import _try_refresh_autorespond

    callback = MagicMock()
    callback.answer = AsyncMock()
    i18n = MagicMock()
    i18n.get = MagicMock(return_value="ok")
    svc = MagicMock()
    svc.update_celery_task_id = AsyncMock()

    items = [{"autoparsed_vacancy_id": 1, "hh_vacancy_id": "9", "resume_id": "r", "vacancy_url": "u"}]
    resume = {
        "user_id": 1,
        "chat_id": 2,
        "message_id": 0,
        "locale": "ru",
        "hh_linked_account_id": 3,
        "feed_session_id": 0,
        "cover_letter_style": "x",
        "cover_task_enabled": True,
        "silent_feed": True,
        "autorespond_progress": {},
    }

    with (
        patch(
            "src.bot.modules.progress.handlers.is_autorespond_cancelled_sync",
            return_value=False,
        ),
        patch(
            "src.bot.modules.progress.handlers.load_hh_ui_batch_checkpoint_full_sync",
            return_value=(items, resume),
        ),
        patch(
            "src.bot.modules.progress.handlers.load_autorespond_ui_tail_sync",
            return_value=[],
        ),
        patch(
            "src.bot.modules.progress.handlers.get_hh_ui_batch_active_sync",
            return_value="celery-active-id",
        ),
        patch(
            "src.bot.modules.progress.handlers.celery_task_id_is_active",
            return_value=True,
        ),
        patch(
            "src.bot.modules.progress.handlers.run_sync_in_thread",
            new_callable=AsyncMock,
        ) as mock_sync,
        patch(
            "src.bot.modules.progress.handlers.clear_hh_ui_batch_active_sync",
        ) as mock_clear_active,
        patch(
            "src.bot.modules.progress.handlers.run_celery_task",
            new_callable=AsyncMock,
        ) as mock_run,
    ):
        mock_run.return_value = MagicMock(id="new-id")
        await _try_refresh_autorespond(
            callback, i18n, "autorespond:8:tid", 2, svc
        )

    mock_sync.assert_awaited_once()
    sync_args, sync_kw = mock_sync.call_args
    assert sync_args[1] == "celery-active-id"
    assert sync_kw.get("terminate") is True
    mock_clear_active.assert_called_once_with(2, "autorespond:8:tid")
    mock_run.assert_awaited_once()
