"""Unit tests for autorespond loop timeout helpers."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_tick_autorespond_bar_bounded_logs_on_timeout() -> None:
    async def slow_tick(**kwargs):
        await asyncio.sleep(60)

    with (
        patch(
            "src.services.autorespond_progress.tick_autorespond_bar",
            side_effect=slow_tick,
        ),
        patch("src.worker.tasks.autorespond.settings") as mock_settings,
    ):
        mock_settings.autorespond_progress_tick_timeout_seconds = 0.05
        from src.worker.tasks.autorespond import _tick_autorespond_bar_bounded

        await _tick_autorespond_bar_bounded(chat_id=1, task_key="k", total=1, locale="ru")


@pytest.mark.asyncio
async def test_resolve_resume_bounded_falls_back_on_timeout() -> None:
    async def slow_resolve(*args, **kwargs):
        await asyncio.sleep(60)
        return "never"

    resume_items = [{"id": "aaa111", "title": "A"}, {"id": "bbb222", "title": "B"}]
    vac = type("V", (), {"id": 9, "hh_vacancy_id": "123"})()

    with (
        patch(
            "src.services.ai.resume_selection.resolve_resume_id_for_autorespond_vacancy",
            side_effect=slow_resolve,
        ),
        patch("src.worker.tasks.autorespond.settings") as mock_settings,
    ):
        mock_settings.autorespond_resume_resolve_timeout_seconds = 0.05
        from src.worker.tasks.autorespond import _resolve_resume_for_autorespond_bounded

        picked = await _resolve_resume_for_autorespond_bounded(
            None,
            vac,
            resume_items,
            stored_autorespond_resume_id=None,
        )
    assert picked == "aaa111"
