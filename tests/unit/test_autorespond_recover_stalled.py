"""Recovery sweep: re-enqueues stalled pumps; clears converged or cancelled runs."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_recover_stalled_does_nothing_when_pump_heartbeat_fresh() -> None:
    delay_mock = MagicMock()
    cleared_mock = MagicMock()

    with (
        patch(
            "src.worker.tasks.autorespond.iter_active_pipeline_envelopes",
            return_value=[(42, "autorespond:1:abc")],
        ),
        patch(
            "src.worker.tasks.autorespond.load_pipeline_envelope",
            return_value={
                "resume_envelope": {
                    "user_id": 7,
                    "chat_id": 42,
                    "hh_linked_account_id": 5,
                },
            },
        ),
        patch(
            "src.worker.tasks.autorespond.ready_remaining_count",
            return_value=5,
        ),
        patch(
            "src.worker.tasks.autorespond.pump_heartbeat_age_seconds",
            return_value=10.0,
        ),
        patch(
            "src.worker.tasks.autorespond.get_pump_lock_owner_sync",
            return_value=None,
        ),
        patch(
            "src.services.autorespond_progress.is_autorespond_cancelled_sync",
            return_value=False,
        ),
        patch(
            "src.services.autorespond_pipeline_state.pregen_pending_count",
            return_value=2,
        ),
        patch(
            "src.worker.tasks.hh_ui_apply.apply_pump_task",
            MagicMock(delay=delay_mock),
        ),
        patch(
            "src.worker.tasks.autorespond.clear_all_pipeline_state",
            cleared_mock,
        ),
        patch("src.worker.tasks.autorespond.settings") as mock_settings,
    ):
        mock_settings.autorespond_recover_stalled_pump_grace_seconds = 90

        from src.worker.tasks.autorespond import _recover_stalled_pipelines_async

        res = await _recover_stalled_pipelines_async()

    assert res["inspected"] == 1
    assert res["healed"] == 0
    assert res["cleared"] == 0
    delay_mock.assert_not_called()
    cleared_mock.assert_not_called()


@pytest.mark.asyncio
async def test_recover_stalled_reenqueues_pump_when_heartbeat_stale() -> None:
    delay_mock = MagicMock()

    with (
        patch(
            "src.worker.tasks.autorespond.iter_active_pipeline_envelopes",
            return_value=[(42, "autorespond:1:abc")],
        ),
        patch(
            "src.worker.tasks.autorespond.load_pipeline_envelope",
            return_value={
                "resume_envelope": {
                    "user_id": 7,
                    "chat_id": 42,
                    "hh_linked_account_id": 5,
                    "autorespond_progress": {"task_key": "autorespond:1:abc", "total": 5},
                },
            },
        ),
        patch(
            "src.worker.tasks.autorespond.ready_remaining_count",
            return_value=3,
        ),
        patch(
            "src.worker.tasks.autorespond.pump_heartbeat_age_seconds",
            return_value=600.0,
        ),
        patch(
            "src.worker.tasks.autorespond.get_pump_lock_owner_sync",
            return_value=None,
        ),
        patch(
            "src.services.autorespond_progress.is_autorespond_cancelled_sync",
            return_value=False,
        ),
        patch(
            "src.services.autorespond_pipeline_state.pregen_pending_count",
            return_value=0,
        ),
        patch(
            "src.worker.tasks.hh_ui_apply.apply_pump_task",
            MagicMock(delay=delay_mock),
        ),
        patch("src.worker.tasks.autorespond.settings") as mock_settings,
    ):
        mock_settings.autorespond_recover_stalled_pump_grace_seconds = 90

        from src.worker.tasks.autorespond import _recover_stalled_pipelines_async

        res = await _recover_stalled_pipelines_async()

    assert res["healed"] == 1
    delay_mock.assert_called_once()


@pytest.mark.asyncio
async def test_recover_stalled_skips_when_pump_lock_held() -> None:
    delay_mock = MagicMock()

    with (
        patch(
            "src.worker.tasks.autorespond.iter_active_pipeline_envelopes",
            return_value=[(42, "autorespond:1:abc")],
        ),
        patch(
            "src.worker.tasks.autorespond.load_pipeline_envelope",
            return_value={"resume_envelope": {"user_id": 7, "chat_id": 42}},
        ),
        patch(
            "src.worker.tasks.autorespond.ready_remaining_count",
            return_value=3,
        ),
        patch(
            "src.worker.tasks.autorespond.get_pump_lock_owner_sync",
            return_value="active-pump-task",
        ),
        patch(
            "src.worker.tasks.autorespond.pump_heartbeat_age_seconds",
            return_value=600.0,
        ),
        patch(
            "src.services.autorespond_progress.is_autorespond_cancelled_sync",
            return_value=False,
        ),
        patch(
            "src.services.autorespond_pipeline_state.pregen_pending_count",
            return_value=0,
        ),
        patch(
            "src.worker.tasks.hh_ui_apply.apply_pump_task",
            MagicMock(delay=delay_mock),
        ),
        patch("src.worker.tasks.autorespond.settings") as mock_settings,
    ):
        mock_settings.autorespond_recover_stalled_pump_grace_seconds = 90

        from src.worker.tasks.autorespond import _recover_stalled_pipelines_async

        res = await _recover_stalled_pipelines_async()

    assert res["healed"] == 0
    delay_mock.assert_not_called()


@pytest.mark.asyncio
async def test_recover_stalled_clears_state_when_cancelled() -> None:
    delay_mock = MagicMock()
    cleared_mock = MagicMock()

    with (
        patch(
            "src.worker.tasks.autorespond.iter_active_pipeline_envelopes",
            return_value=[(42, "autorespond:1:abc")],
        ),
        patch(
            "src.worker.tasks.autorespond.load_pipeline_envelope",
            return_value={"resume_envelope": {}},
        ),
        patch(
            "src.services.autorespond_progress.is_autorespond_cancelled_sync",
            return_value=True,
        ),
        patch(
            "src.worker.tasks.autorespond.clear_all_pipeline_state",
            cleared_mock,
        ),
        patch(
            "src.worker.tasks.hh_ui_apply.apply_pump_task",
            MagicMock(delay=delay_mock),
        ),
        patch("src.worker.tasks.autorespond.settings") as mock_settings,
    ):
        mock_settings.autorespond_recover_stalled_pump_grace_seconds = 90

        from src.worker.tasks.autorespond import _recover_stalled_pipelines_async

        res = await _recover_stalled_pipelines_async()

    assert res["cleared"] == 1
    cleared_mock.assert_called_once_with(42, "autorespond:1:abc")
    delay_mock.assert_not_called()


@pytest.mark.asyncio
async def test_recover_stalled_clears_state_when_run_converged() -> None:
    """Bar reached 100% — ready ZSET empty + no pregens pending → cleanup."""
    cleared_mock = MagicMock()

    with (
        patch(
            "src.worker.tasks.autorespond.iter_active_pipeline_envelopes",
            return_value=[(42, "autorespond:1:abc")],
        ),
        patch(
            "src.worker.tasks.autorespond.load_pipeline_envelope",
            return_value={"resume_envelope": {}},
        ),
        patch(
            "src.services.autorespond_progress.is_autorespond_cancelled_sync",
            return_value=False,
        ),
        patch(
            "src.worker.tasks.autorespond.ready_remaining_count",
            return_value=0,
        ),
        patch(
            "src.services.autorespond_pipeline_state.pregen_pending_count",
            return_value=0,
        ),
        patch(
            "src.worker.tasks.autorespond.clear_all_pipeline_state",
            cleared_mock,
        ),
        patch("src.worker.tasks.autorespond.settings") as mock_settings,
    ):
        mock_settings.autorespond_recover_stalled_pump_grace_seconds = 90

        from src.worker.tasks.autorespond import _recover_stalled_pipelines_async

        res = await _recover_stalled_pipelines_async()

    assert res["cleared"] == 1
    cleared_mock.assert_called_once_with(42, "autorespond:1:abc")
