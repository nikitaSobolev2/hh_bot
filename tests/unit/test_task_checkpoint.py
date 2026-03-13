"""Unit tests for TaskCheckpointService."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.task_checkpoint import TaskCheckpointService


def _make_redis(*, stored: str | None = None) -> MagicMock:
    redis = MagicMock()
    redis.get = AsyncMock(return_value=stored)
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    return redis


class TestSave:
    @pytest.mark.asyncio
    async def test_serialises_payload_as_json_and_sets_ttl(self):
        redis = _make_redis()
        service = TaskCheckpointService(redis)

        await service.save("autoparse:42", "task-abc", analyzed=33, total=86)

        redis.set.assert_called_once()
        call_args = redis.set.call_args
        key = call_args.args[0]
        payload = json.loads(call_args.args[1])
        ttl = call_args.kwargs["ex"]

        assert key == "checkpoint:autoparse:42"
        assert payload == {"task_id": "task-abc", "analyzed": 33, "total": 86}
        assert ttl == 4 * 3600

    @pytest.mark.asyncio
    async def test_overwrites_existing_entry(self):
        redis = _make_redis()
        service = TaskCheckpointService(redis)

        await service.save("autoparse:1", "t1", analyzed=10, total=50)
        await service.save("autoparse:1", "t1", analyzed=20, total=50)

        assert redis.set.call_count == 2
        last_payload = json.loads(redis.set.call_args.args[1])
        assert last_payload["analyzed"] == 20


class TestLoad:
    @pytest.mark.asyncio
    async def test_returns_analyzed_and_total_when_task_id_matches(self):
        stored = json.dumps({"task_id": "task-abc", "analyzed": 33, "total": 86})
        redis = _make_redis(stored=stored)
        service = TaskCheckpointService(redis)

        result = await service.load("autoparse:42", "task-abc")

        assert result == (33, 86)

    @pytest.mark.asyncio
    async def test_returns_none_when_task_id_differs(self):
        stored = json.dumps({"task_id": "task-old", "analyzed": 10, "total": 50})
        redis = _make_redis(stored=stored)
        service = TaskCheckpointService(redis)

        result = await service.load("autoparse:42", "task-new")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_key_absent(self):
        redis = _make_redis(stored=None)
        service = TaskCheckpointService(redis)

        result = await service.load("autoparse:99", "task-xyz")

        assert result is None

    @pytest.mark.asyncio
    async def test_queries_correct_redis_key(self):
        redis = _make_redis(stored=None)
        service = TaskCheckpointService(redis)

        await service.load("autoparse:7", "t")

        redis.get.assert_called_once_with("checkpoint:autoparse:7")

    @pytest.mark.asyncio
    async def test_returns_zero_analyzed_when_checkpoint_has_zero(self):
        stored = json.dumps({"task_id": "t", "analyzed": 0, "total": 50})
        redis = _make_redis(stored=stored)
        service = TaskCheckpointService(redis)

        result = await service.load("autoparse:1", "t")

        assert result == (0, 50)


class TestSaveParsing:
    @pytest.mark.asyncio
    async def test_serialises_urls_and_sets_ttl(self):
        redis = _make_redis()
        service = TaskCheckpointService(redis)
        urls = [{"url": "https://hh.ru/vacancy/1", "title": "Test", "hh_vacancy_id": "1"}]

        await service.save_parsing("parse:42", "task-abc", processed=10, total=50, urls=urls)

        redis.set.assert_called_once()
        call_args = redis.set.call_args
        payload = json.loads(call_args.args[1])
        assert payload["task_id"] == "task-abc"
        assert payload["processed"] == 10
        assert payload["total"] == 50
        assert payload["urls"] == urls

    @pytest.mark.asyncio
    async def test_uses_correct_redis_key(self):
        redis = _make_redis()
        service = TaskCheckpointService(redis)

        await service.save_parsing("parse:7", "t", processed=0, total=10, urls=[])

        assert redis.set.call_args.args[0] == "checkpoint:parse:7"


class TestLoadParsing:
    @pytest.mark.asyncio
    async def test_returns_processed_total_urls_when_task_id_matches(self):
        urls = [{"url": "x", "hh_vacancy_id": "1"}]
        stored = json.dumps({"task_id": "task-abc", "processed": 5, "total": 20, "urls": urls})
        redis = _make_redis(stored=stored)
        service = TaskCheckpointService(redis)

        result = await service.load_parsing("parse:42", "task-abc")

        assert result == (5, 20, urls)

    @pytest.mark.asyncio
    async def test_returns_none_when_task_id_differs(self):
        stored = json.dumps({"task_id": "old", "processed": 5, "total": 20, "urls": [{}]})
        redis = _make_redis(stored=stored)
        service = TaskCheckpointService(redis)

        result = await service.load_parsing("parse:42", "new")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_urls_empty(self):
        stored = json.dumps({"task_id": "t", "processed": 5, "total": 20, "urls": []})
        redis = _make_redis(stored=stored)
        service = TaskCheckpointService(redis)

        result = await service.load_parsing("parse:42", "t")

        assert result is None


class TestLoadParsingForResume:
    @pytest.mark.asyncio
    async def test_returns_data_when_task_id_differs(self):
        urls = [{"url": "x", "hh_vacancy_id": "1"}]
        stored = json.dumps({"task_id": "old-task", "processed": 5, "total": 20, "urls": urls})
        redis = _make_redis(stored=stored)
        service = TaskCheckpointService(redis)

        result = await service.load_parsing_for_resume("parse:42")

        assert result == (5, 20, urls)

    @pytest.mark.asyncio
    async def test_returns_none_when_key_absent(self):
        redis = _make_redis(stored=None)
        service = TaskCheckpointService(redis)

        result = await service.load_parsing_for_resume("parse:99")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_urls_empty(self):
        stored = json.dumps({"task_id": "t", "processed": 5, "total": 20, "urls": []})
        redis = _make_redis(stored=stored)
        service = TaskCheckpointService(redis)

        result = await service.load_parsing_for_resume("parse:42")

        assert result is None


class TestClear:
    @pytest.mark.asyncio
    async def test_deletes_checkpoint_key(self):
        redis = _make_redis()
        service = TaskCheckpointService(redis)

        await service.clear("autoparse:42")

        redis.delete.assert_called_once_with("checkpoint:autoparse:42")

    @pytest.mark.asyncio
    async def test_clear_is_idempotent_when_key_absent(self):
        redis = _make_redis()
        redis.delete = AsyncMock(return_value=0)
        service = TaskCheckpointService(redis)

        await service.clear("autoparse:missing")

        redis.delete.assert_called_once()
