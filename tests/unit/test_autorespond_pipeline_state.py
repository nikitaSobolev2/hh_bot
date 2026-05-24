"""Redis-backed pipeline-state helpers for the autorespond producer/consumer model."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest


class _FakeRedis:
    """Tiny in-memory drop-in for ``create_sync_redis`` used by pipeline-state helpers."""

    def __init__(self) -> None:
        self.kv: dict[str, str] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.sets: dict[str, set[str]] = {}

    # --- generic
    def get(self, key: str):
        return self.kv.get(key)

    def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        if nx and key in self.kv:
            return None
        self.kv[key] = value
        return True

    def delete(self, *keys: str) -> int:
        n = 0
        for k in keys:
            n += int(k in self.kv)
            n += int(k in self.zsets)
            n += int(k in self.hashes)
            n += int(k in self.sets)
            self.kv.pop(k, None)
            self.zsets.pop(k, None)
            self.hashes.pop(k, None)
            self.sets.pop(k, None)
        return n

    def expire(self, key: str, ttl: int) -> bool:
        return key in self.kv or key in self.zsets or key in self.hashes or key in self.sets

    def scan_iter(self, match: str, count: int = 100):
        prefix = match.replace("*", "")
        for k in list(self.kv):
            if k.startswith(prefix):
                yield k

    # --- zset
    def zadd(self, key: str, mapping: dict[str, float]) -> int:
        z = self.zsets.setdefault(key, {})
        new = 0
        for member, score in mapping.items():
            new += int(member not in z)
            z[member] = float(score)
        return new

    def zcard(self, key: str) -> int:
        return len(self.zsets.get(key, {}))

    def zpopmin(self, key: str, count: int = 1) -> list[tuple[str, float]]:
        z = self.zsets.get(key, {})
        if not z:
            return []
        items = sorted(z.items(), key=lambda kv: kv[1])[:count]
        for member, _ in items:
            z.pop(member, None)
        return items

    # --- hash
    def hset(self, key: str, field: str, value: str):
        self.hashes.setdefault(key, {})[field] = value
        return 1

    def hget(self, key: str, field: str):
        return self.hashes.get(key, {}).get(field)

    def hexists(self, key: str, field: str) -> bool:
        return field in self.hashes.get(key, {})

    # --- set
    def sadd(self, key: str, *members: str) -> int:
        s = self.sets.setdefault(key, set())
        new = 0
        for m in members:
            if m not in s:
                new += 1
                s.add(m)
        return new

    def srem(self, key: str, *members: str) -> int:
        s = self.sets.get(key, set())
        n = 0
        for m in members:
            if m in s:
                n += 1
                s.remove(m)
        return n

    def scard(self, key: str) -> int:
        return len(self.sets.get(key, set()))

    def sismember(self, key: str, member: str) -> bool:
        return member in self.sets.get(key, set())

    def close(self) -> None:
        pass

    def pipeline(self):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, parent: _FakeRedis) -> None:
        self._parent = parent
        self._cmds: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, name: str):
        def _record(*args, **kwargs):
            self._cmds.append((name, args, kwargs))
            return self

        return _record

    def execute(self) -> list:
        results = []
        for name, args, kwargs in self._cmds:
            fn = getattr(self._parent, name)
            results.append(fn(*args, **kwargs))
        self._cmds.clear()
        return results


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    fake = _FakeRedis()
    monkeypatch.setattr(
        "src.services.autorespond_pipeline_state.create_sync_redis",
        lambda: fake,
    )
    return fake


def test_seed_ready_to_apply_adds_specs_and_skips_invalid(fake_redis: _FakeRedis) -> None:
    from src.services.autorespond_pipeline_state import (
        ready_remaining_count,
        seed_ready_to_apply,
    )

    specs = [
        {"autoparsed_vacancy_id": 10, "hh_vacancy_id": "1", "resume_id": "r", "vacancy_url": "u"},
        {"autoparsed_vacancy_id": 11, "hh_vacancy_id": "2", "resume_id": "r", "vacancy_url": "u"},
        {"bad": "spec"},
    ]
    added = seed_ready_to_apply(chat_id=7, task_key="t", items=specs)
    assert added == 2
    assert ready_remaining_count(7, "t") == 2


def test_pop_ready_batch_returns_specs_in_score_order(fake_redis: _FakeRedis) -> None:
    from src.services.autorespond_pipeline_state import (
        pop_ready_batch,
        seed_ready_to_apply,
    )

    seed_ready_to_apply(
        7,
        "t",
        [
            {
                "autoparsed_vacancy_id": 100,
                "hh_vacancy_id": "a",
                "resume_id": "r",
                "vacancy_url": "u",
            },
            {
                "autoparsed_vacancy_id": 200,
                "hh_vacancy_id": "b",
                "resume_id": "r",
                "vacancy_url": "u",
            },
        ],
    )
    batch = pop_ready_batch(7, "t", batch_size=10)
    assert {b["autoparsed_vacancy_id"] for b in batch} == {100, 200}
    assert batch[0]["autoparsed_vacancy_id"] == 200  # newest (negated score)


def test_store_pregen_letter_removes_from_pending_and_caches(fake_redis: _FakeRedis) -> None:
    from src.services.autorespond_pipeline_state import (
        fetch_pregen_letter,
        mark_pregen_pending,
        pregen_letter_exists,
        pregen_pending_count,
        store_pregen_letter,
    )

    mark_pregen_pending(7, "t", [1, 2, 3])
    assert pregen_pending_count(7, "t") == 3
    store_pregen_letter(7, "t", 2, "hello")
    assert pregen_pending_count(7, "t") == 2
    assert pregen_letter_exists(7, "t", 2)
    assert fetch_pregen_letter(7, "t", 2) == "hello"
    assert fetch_pregen_letter(7, "t", 99) is None


def test_is_pregen_pending_for_vacancy(fake_redis: _FakeRedis) -> None:
    from src.services.autorespond_pipeline_state import (
        is_pregen_pending_for_vacancy,
        mark_pregen_pending,
        release_pregen_pending,
    )

    assert is_pregen_pending_for_vacancy(7, "t", 11) is False
    mark_pregen_pending(7, "t", [11, 12])
    assert is_pregen_pending_for_vacancy(7, "t", 11) is True
    assert is_pregen_pending_for_vacancy(7, "t", 99) is False
    release_pregen_pending(7, "t", [11])
    assert is_pregen_pending_for_vacancy(7, "t", 11) is False


def test_pump_lock_exclusive_per_run(fake_redis: _FakeRedis) -> None:
    from src.services.autorespond_pipeline_state import (
        clear_pump_lock,
        get_pump_lock_owner_sync,
        release_pump_lock,
        try_acquire_pump_lock,
    )

    assert try_acquire_pump_lock(7, "t", "owner-a") is True
    assert get_pump_lock_owner_sync(7, "t") == "owner-a"
    assert try_acquire_pump_lock(7, "t", "owner-b") is False
    release_pump_lock(7, "t", "owner-a")
    assert try_acquire_pump_lock(7, "t", "owner-b") is True
    clear_pump_lock(7, "t")
    assert get_pump_lock_owner_sync(7, "t") is None


def test_pump_heartbeat_age_seconds_returns_fresh_value(fake_redis: _FakeRedis) -> None:
    from src.services.autorespond_pipeline_state import (
        pump_heartbeat_age_seconds,
        touch_pump_heartbeat,
    )

    assert pump_heartbeat_age_seconds(7, "t") is None
    touch_pump_heartbeat(7, "t")
    age = pump_heartbeat_age_seconds(7, "t")
    assert age is not None
    assert 0 <= age < 2


def test_is_apply_pump_active_when_lock_held(fake_redis: _FakeRedis) -> None:
    from src.services.autorespond_pipeline_state import (
        is_apply_pump_active,
        try_acquire_pump_lock,
    )

    assert is_apply_pump_active(7, "t") is False
    assert try_acquire_pump_lock(7, "t", "owner-a") is True
    assert is_apply_pump_active(7, "t") is True


def test_kick_apply_pump_skips_when_pump_active(fake_redis: _FakeRedis) -> None:
    from src.services.autorespond_pipeline_state import (
        kick_apply_pump_for_pipeline,
        save_pipeline_envelope,
        try_acquire_pump_lock,
    )

    save_pipeline_envelope(
        7,
        "t",
        {"resume_envelope": {"user_id": 1, "hh_linked_account_id": 2, "chat_id": 7}},
    )
    assert try_acquire_pump_lock(7, "t", "owner-a") is True
    with patch("src.worker.tasks.hh_ui_apply.apply_pump_task") as pump_task:
        kick_apply_pump_for_pipeline(7, "t")
        pump_task.delay.assert_not_called()


def test_clear_all_pipeline_state_wipes_every_key(fake_redis: _FakeRedis) -> None:
    from src.services.autorespond_pipeline_state import (
        clear_all_pipeline_state,
        mark_pregen_pending,
        pregen_pending_count,
        ready_remaining_count,
        save_pipeline_envelope,
        seed_ready_to_apply,
        store_pregen_letter,
        touch_pump_heartbeat,
    )

    seed_ready_to_apply(
        7,
        "t",
        [
            {
                "autoparsed_vacancy_id": 1,
                "hh_vacancy_id": "x",
                "resume_id": "r",
                "vacancy_url": "u",
            }
        ],
    )
    mark_pregen_pending(7, "t", [1])
    store_pregen_letter(7, "t", 9, "letter")
    touch_pump_heartbeat(7, "t")
    save_pipeline_envelope(7, "t", {"x": 1})

    clear_all_pipeline_state(7, "t")
    assert ready_remaining_count(7, "t") == 0
    assert pregen_pending_count(7, "t") == 0


def test_iter_active_pipeline_envelopes_yields_chat_and_task(fake_redis: _FakeRedis) -> None:
    from src.services.autorespond_pipeline_state import (
        iter_active_pipeline_envelopes,
        save_pipeline_envelope,
    )

    save_pipeline_envelope(7, "autorespond:1:abc", {"v": 1})
    save_pipeline_envelope(8, "autorespond:2:xyz", {"v": 2})
    found = set(iter_active_pipeline_envelopes())
    assert (7, "autorespond:1:abc") in found
    assert (8, "autorespond:2:xyz") in found


def test_save_pipeline_envelope_roundtrips_json(fake_redis: _FakeRedis) -> None:
    from src.services.autorespond_pipeline_state import (
        load_pipeline_envelope,
        pipeline_envelope_key,
        save_pipeline_envelope,
    )

    save_pipeline_envelope(7, "t", {"resume_envelope": {"user_id": 11}, "total": 5})
    loaded = load_pipeline_envelope(7, "t")
    assert loaded == {"resume_envelope": {"user_id": 11}, "total": 5}
    raw = fake_redis.kv[pipeline_envelope_key(7, "t")]
    assert json.loads(raw)["total"] == 5
