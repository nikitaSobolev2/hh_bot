"""Tail-chain recovery when parent autorespond stops dispatching."""

from __future__ import annotations

from unittest.mock import patch

from src.worker.tasks.hh_ui_apply import _maybe_enqueue_next_ui_batch_from_tail


def test_tail_chain_skips_when_parent_heartbeat_fresh_and_on_workers() -> None:
    with (
        patch(
            "src.services.autorespond_progress.should_defer_ui_tail_chain_to_parent_sync",
            return_value=(True, "parent_dispatching"),
        ) as defer_mock,
        patch(
            "src.worker.tasks.hh_ui_apply.apply_to_vacancies_batch_ui_task",
        ) as delay_mock,
    ):
        _maybe_enqueue_next_ui_batch_from_tail(
            user_id=1,
            chat_id=99,
            message_id=0,
            locale="ru",
            hh_linked_account_id=1,
            feed_session_id=0,
            cover_letter_style="formal",
            cover_task_enabled=True,
            silent_feed=True,
            autorespond_progress={
                "task_key": "pipeline:2:parent-id",
                "celery_task_id": "parent-id",
            },
            batch_result={"status": "ok", "processed": 4},
        )
    defer_mock.assert_called_once()
    delay_mock.delay.assert_not_called()


def test_tail_chain_recovers_when_parent_heartbeat_stale() -> None:
    tail_item = {
        "autoparsed_vacancy_id": 5,
        "hh_vacancy_id": "555",
        "resume_id": "r1",
        "vacancy_url": "https://hh.ru/vacancy/555",
    }
    with (
        patch(
            "src.services.autorespond_progress.should_defer_ui_tail_chain_to_parent_sync",
            return_value=(False, "heartbeat_stale_parent_wedged"),
        ),
        patch(
            "src.services.autorespond_progress.clear_autorespond_parent_loop_active_sync",
        ) as clear_mock,
        patch(
            "src.services.autorespond_progress.pop_autorespond_ui_tail_batch_sync",
            return_value=[tail_item],
        ),
        patch(
            "src.services.autorespond_progress.save_hh_ui_resume_envelope_sync",
        ),
        patch(
            "src.worker.tasks.hh_ui_apply.apply_to_vacancies_batch_ui_task",
        ) as delay_mock,
    ):
        _maybe_enqueue_next_ui_batch_from_tail(
            user_id=1,
            chat_id=99,
            message_id=0,
            locale="ru",
            hh_linked_account_id=1,
            feed_session_id=0,
            cover_letter_style="formal",
            cover_task_enabled=True,
            silent_feed=True,
            autorespond_progress={
                "task_key": "pipeline:2:parent-id",
                "celery_task_id": "parent-id",
            },
            batch_result={"status": "ok", "processed": 4},
        )
    clear_mock.assert_called_once_with(99, "pipeline:2:parent-id")
    delay_mock.delay.assert_called_once()
    kwargs = delay_mock.delay.call_args.kwargs
    assert kwargs["items"] == [tail_item]


def test_should_defer_false_when_parent_not_on_workers() -> None:
    from src.services.autorespond_progress import should_defer_ui_tail_chain_to_parent_sync

    with (
        patch(
            "src.services.autorespond_progress.is_autorespond_parent_loop_active_sync",
            return_value=True,
        ),
        patch(
            "src.services.autorespond_progress.is_autorespond_parent_loop_heartbeat_stale_sync",
            return_value=False,
        ),
        patch(
            "src.services.celery_active.celery_task_id_is_active",
            return_value=False,
        ),
    ):
        defer, reason = should_defer_ui_tail_chain_to_parent_sync(
            99,
            "pipeline:2:dead",
            "dead-parent",
            heartbeat_stale_seconds=120.0,
        )
    assert defer is False
    assert reason == "parent_task_not_on_workers"


def test_should_defer_true_only_when_heartbeat_fresh_and_parent_active() -> None:
    from src.services.autorespond_progress import should_defer_ui_tail_chain_to_parent_sync

    with (
        patch(
            "src.services.autorespond_progress.is_autorespond_parent_loop_active_sync",
            return_value=True,
        ),
        patch(
            "src.services.autorespond_progress.is_autorespond_parent_loop_heartbeat_stale_sync",
            return_value=False,
        ),
        patch(
            "src.services.celery_active.celery_task_id_is_active",
            return_value=True,
        ),
    ):
        defer, reason = should_defer_ui_tail_chain_to_parent_sync(
            99,
            "pipeline:2:live",
            "live-parent",
            heartbeat_stale_seconds=120.0,
        )
    assert defer is True
    assert reason == "parent_dispatching"
