"""Unit tests for streaming autorespond feed."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _vac(
    *,
    vid: int,
    hh_id: str = "hh-1",
    score: float = 80.0,
    title: str = "Python Dev",
    needs_eq: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=vid,
        hh_vacancy_id=hh_id,
        compatibility_score=score,
        title=title,
        description="python backend",
        url=f"https://hh.ru/vacancy/{hh_id}",
        needs_employer_questions=needs_eq,
    )


@pytest.mark.asyncio
async def test_on_autoparsed_rows_enqueues_when_compat_ready() -> None:
    from src.services.autorespond_streaming import (
        StreamingAutorespondContext,
        StreamingAutorespondFeed,
    )

    progress = MagicMock()
    progress.update_bar = AsyncMock()
    progress.set_nested_step_state = AsyncMock()
    progress.update_footer = AsyncMock()

    ctx = StreamingAutorespondContext(
        session_factory=MagicMock(),
        company_id=1,
        user_id=7,
        chat_id=99,
        task_key="pipeline:1:abc",
        locale="ru",
        celery_task_id="celery-1",
        hh_linked_account_id=2,
        progress=progress,
        progress_bot=MagicMock(),
    )
    feed = StreamingAutorespondFeed(ctx)
    feed._company = SimpleNamespace(
        autorespond_min_compat=50,
        autorespond_keyword_mode="title_only",
        keyword_filter="",
        keyword_check_enabled=False,
        autorespond_resume_id="r1",
        vacancy_title="Backend",
    )
    feed._resume_items = [{"id": "r1"}]
    feed._cover_task_enabled = False

    with (
        patch.object(feed, "_load_company_context", new=AsyncMock(return_value=True)),
        patch.object(feed, "_already_handled", new=AsyncMock(return_value=set())),
        patch(
            "src.worker.tasks.autorespond._resolve_resume_for_autorespond_bounded",
            new=AsyncMock(return_value="r1"),
        ),
        patch("src.services.autorespond_streaming.seed_ready_to_apply", return_value=1),
        patch("src.services.autorespond_streaming.save_pipeline_envelope"),
        patch(
            "src.services.autorespond_streaming.get_autorespond_done_count_sync",
            return_value=0,
        ),
        patch.object(feed, "_kick_pump_if_needed", new=AsyncMock()) as pump_mock,
    ):
        enqueued = await feed.on_autoparsed_rows([_vac(vid=42)])

    assert enqueued == 1
    assert feed._work_units == 1
    assert 42 in feed._enqueued_ids
    pump_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_autoparsed_rows_skips_without_compatibility_score() -> None:
    from src.services.autorespond_streaming import (
        StreamingAutorespondContext,
        StreamingAutorespondFeed,
    )

    ctx = StreamingAutorespondContext(
        session_factory=MagicMock(),
        company_id=1,
        user_id=7,
        chat_id=99,
        task_key="pipeline:1:abc",
        locale="ru",
        celery_task_id="celery-1",
        hh_linked_account_id=2,
        progress=MagicMock(),
        progress_bot=MagicMock(),
    )
    feed = StreamingAutorespondFeed(ctx)
    feed._company = SimpleNamespace(
        autorespond_min_compat=50,
        autorespond_keyword_mode="title_only",
        keyword_filter="",
        keyword_check_enabled=False,
        autorespond_resume_id="r1",
        vacancy_title="Backend",
    )
    feed._resume_items = [{"id": "r1"}]

    with (
        patch.object(feed, "_load_company_context", new=AsyncMock(return_value=True)),
        patch.object(feed, "_already_handled", new=AsyncMock(return_value=set())),
    ):
        enqueued = await feed.on_autoparsed_rows([_vac(vid=42, score=0.0)])

    assert enqueued == 0
    assert feed._work_units == 0


@pytest.mark.asyncio
async def test_finalize_marks_streaming_parse_complete() -> None:
    from src.services.autorespond_streaming import (
        StreamingAutorespondContext,
        StreamingAutorespondFeed,
    )

    ctx = StreamingAutorespondContext(
        session_factory=MagicMock(),
        company_id=1,
        user_id=7,
        chat_id=99,
        task_key="pipeline:1:abc",
        locale="ru",
        celery_task_id="celery-1",
        hh_linked_account_id=2,
        progress=MagicMock(),
        progress_bot=MagicMock(),
    )
    feed = StreamingAutorespondFeed(ctx)
    feed._work_units = 2

    with (
        patch(
            "src.services.autorespond_streaming.mark_streaming_parse_complete",
        ) as mark_done,
        patch(
            "src.services.autorespond_streaming.maybe_finish_streaming_autorespond_progress",
            new_callable=AsyncMock,
        ) as maybe_finish,
    ):
        result = await feed.finalize()

    mark_done.assert_called_once_with(99, "pipeline:1:abc")
    maybe_finish.assert_awaited_once()
    assert result["queued"] == 2
