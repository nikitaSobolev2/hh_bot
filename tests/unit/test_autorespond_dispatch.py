"""Autorespond dispatcher: filter → resume-pick → seed ZSET → fan-out pregens → kick pump."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _vac(*, vid: int, hh_id: str, score: float = 90.0) -> SimpleNamespace:
    return SimpleNamespace(
        id=vid,
        hh_vacancy_id=hh_id,
        title="Backend",
        description="",
        url=f"https://hh.ru/vacancy/{hh_id}",
        compatibility_score=score,
        needs_employer_questions=False,
        raw_skills=[],
        ai_summary=None,
        ai_stack=None,
    )


def _make_session_factory() -> tuple[MagicMock, MagicMock]:
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session_factory = MagicMock(return_value=session)
    return session, session_factory


@pytest.mark.asyncio
async def test_dispatch_filters_capped_pre_skipped_and_seeds_ready_zset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dispatcher must: filter via autorespond_logic, skip already-handled, seed ZSET, kick pump."""
    session, session_factory = _make_session_factory()

    settings_repo = MagicMock()
    settings_repo.get_value = AsyncMock(return_value=True)

    company = SimpleNamespace(
        id=11,
        is_deleted=False,
        autorespond_enabled=True,
        autorespond_hh_linked_account_id=5,
        autorespond_min_compat=50,
        autorespond_max_per_run=-1,
        autorespond_keyword_mode="title_only",
        autorespond_resume_id="r1",
        keyword_filter="",
        keyword_check_enabled=False,
        vacancy_title="Backend",
        user_id=7,
    )
    company_repo = MagicMock()
    company_repo.get_by_id = AsyncMock(return_value=company)

    user = SimpleNamespace(id=7, telegram_id=42, language_code="ru")
    user_repo = MagicMock()
    user_repo.get_by_id = AsyncMock(return_value=user)

    hh_acc = SimpleNamespace(resume_list_cache=[{"id": "r1", "title": "Senior Backend"}])
    hh_repo = MagicMock()
    hh_repo.get_by_id = AsyncMock(return_value=hh_acc)

    vacancies = [_vac(vid=101, hh_id="aaa"), _vac(vid=102, hh_id="bbb")]
    we_repo = MagicMock()
    we_repo.get_active_by_user = AsyncMock(return_value=[])

    attempt_repo = MagicMock()
    attempt_repo.hh_vacancy_ids_with_success_or_employer_questions = AsyncMock(
        return_value={"bbb"},  # vid=102 already applied, pre-skipped
    )

    # Local-import paths use the source modules; patch repos there too.
    monkeypatch.setattr(
        "src.repositories.app_settings.AppSettingRepository", lambda *_a, **_k: settings_repo
    )
    monkeypatch.setattr(
        "src.repositories.autoparse.AutoparseCompanyRepository", lambda *_a, **_k: company_repo
    )
    monkeypatch.setattr("src.repositories.user.UserRepository", lambda *_a, **_k: user_repo)
    monkeypatch.setattr(
        "src.repositories.hh_linked_account.HhLinkedAccountRepository",
        lambda *_a, **_k: hh_repo,
    )
    monkeypatch.setattr(
        "src.repositories.work_experience.WorkExperienceRepository",
        lambda *_a, **_k: we_repo,
    )
    monkeypatch.setattr(
        "src.repositories.hh_application_attempt.HhApplicationAttemptRepository",
        lambda *_a, **_k: attempt_repo,
    )
    monkeypatch.setattr(
        "src.worker.tasks.autorespond._load_candidates",
        AsyncMock(return_value=vacancies),
    )
    monkeypatch.setattr(
        "src.worker.tasks.autorespond._regenerate_missing_compatibility_scores",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "src.worker.tasks.autorespond._run_negotiations_sync_with_retry",
        AsyncMock(return_value={"status": "ok"}),
    )
    import src.bot.modules.autoparse.services as _ap_services_mod

    monkeypatch.setattr(
        _ap_services_mod,
        "get_user_autoparse_settings",
        AsyncMock(return_value={"cover_letter_style": "professional"}),
    )

    progress = MagicMock()
    for method in (
        "set_nested_step_state",
        "set_step_state",
        "set_active_step_index",
        "set_nested_active_step_index",
        "set_nested_steps",
        "clear_nested_steps",
        "update_bar",
        "update_footer",
        "finish_task",
        "cancel_task",
    ):
        setattr(progress, method, AsyncMock())

    progress_bot = MagicMock()
    progress_bot.session.close = AsyncMock()

    monkeypatch.setattr(
        "src.worker.tasks.autorespond._start_or_update_progress_bar",
        AsyncMock(return_value=(progress, "autorespond:11:tid", progress_bot, 0, False)),
    )

    # Block real Redis calls from progress helpers used by the dispatcher.
    for fn in (
        "clear_autorespond_done_counter",
        "clear_autorespond_failed_counter",
        "clear_autorespond_employer_test_counter",
    ):
        monkeypatch.setattr(
            f"src.services.autorespond_progress.{fn}", AsyncMock()
        )
    for fn in (
        "clear_hh_ui_batch_checkpoint_sync",
        "clear_hh_ui_resume_envelope_sync",
    ):
        monkeypatch.setattr(f"src.services.autorespond_progress.{fn}", MagicMock())

    # Capture pipeline state writes + delegations.
    seeded: list[dict] = []
    monkeypatch.setattr(
        "src.worker.tasks.autorespond.seed_ready_to_apply",
        lambda chat_id, task_key, items: seeded.extend(items) or len(items),
    )
    pending_marked: list[int] = []
    monkeypatch.setattr(
        "src.worker.tasks.autorespond.mark_pregen_pending",
        lambda chat_id, task_key, vids: pending_marked.extend(vids),
    )
    monkeypatch.setattr(
        "src.services.autorespond_pipeline_state.clear_pump_lock",
        MagicMock(),
    )
    envelope_calls: list[dict] = []
    monkeypatch.setattr(
        "src.worker.tasks.autorespond.save_pipeline_envelope",
        lambda chat_id, task_key, env: envelope_calls.append(env),
    )

    import src.worker.tasks.cover_letter as _cover_mod
    import src.worker.tasks.hh_ui_apply as _hh_ui_mod

    pregen_delay = MagicMock()
    pump_delay = MagicMock()
    monkeypatch.setattr(
        _cover_mod, "pregenerate_for_apply_task", MagicMock(delay=pregen_delay)
    )
    monkeypatch.setattr(_hh_ui_mod, "apply_pump_task", MagicMock(delay=pump_delay))

    # Resume pick uses bounded helper; force it to return resume id without AI.
    monkeypatch.setattr(
        "src.worker.tasks.autorespond._resolve_resume_for_autorespond_bounded",
        AsyncMock(return_value="r1"),
    )

    # _tick_autorespond_bar_bounded should be called once for the pre-skipped vacancy.
    tick_mock = AsyncMock()
    monkeypatch.setattr(
        "src.worker.tasks.autorespond._tick_autorespond_bar_bounded",
        tick_mock,
    )

    # Rate-limit returns "unlimited" so capping by daily quota does not interfere.
    monkeypatch.setattr(
        "src.worker.tasks.autorespond.remaining_ui_apply_slots_sync",
        lambda *_a, **_k: None,
    )

    with patch("src.worker.tasks.autorespond.settings") as mock_settings:
        mock_settings.hh_ui_apply_enabled = True
        mock_settings.autorespond_progress_tick_timeout_seconds = 5

        from src.worker.tasks.autorespond import _run_autorespond_async

        result = await _run_autorespond_async(
            session_factory,
            celery_task=MagicMock(create_bot=MagicMock(return_value=MagicMock())),
            company_id=11,
            vacancy_ids=None,
            trigger="manual",
            task_started_at=None,
        )

    assert result["status"] == "ok"
    assert {s["autoparsed_vacancy_id"] for s in seeded} == {101}  # 102 was pre-skipped
    assert pending_marked == [101]
    assert pregen_delay.call_count == 1
    assert pump_delay.call_count == 1
    assert tick_mock.await_count == 1  # one pre-skip tick
    assert envelope_calls and envelope_calls[0]["resume_envelope"]["user_id"] == 7


@pytest.mark.asyncio
async def test_dispatch_returns_rate_limited_when_no_daily_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, session_factory = _make_session_factory()

    settings_repo = MagicMock()
    settings_repo.get_value = AsyncMock(return_value=True)

    company = SimpleNamespace(
        id=11,
        is_deleted=False,
        autorespond_enabled=True,
        autorespond_hh_linked_account_id=5,
        autorespond_min_compat=50,
        autorespond_max_per_run=-1,
        autorespond_keyword_mode="title_only",
        autorespond_resume_id="r1",
        keyword_filter="",
        keyword_check_enabled=False,
        vacancy_title="Backend",
        user_id=7,
    )
    company_repo = MagicMock()
    company_repo.get_by_id = AsyncMock(return_value=company)
    user = SimpleNamespace(id=7, telegram_id=42, language_code="ru")
    user_repo = MagicMock()
    user_repo.get_by_id = AsyncMock(return_value=user)
    hh_acc = SimpleNamespace(resume_list_cache=[{"id": "r1", "title": "Senior"}])
    hh_repo = MagicMock()
    hh_repo.get_by_id = AsyncMock(return_value=hh_acc)
    we_repo = MagicMock()
    we_repo.get_active_by_user = AsyncMock(return_value=[])

    monkeypatch.setattr(
        "src.repositories.app_settings.AppSettingRepository", lambda *_a, **_k: settings_repo
    )
    monkeypatch.setattr(
        "src.repositories.autoparse.AutoparseCompanyRepository", lambda *_a, **_k: company_repo
    )
    monkeypatch.setattr("src.repositories.user.UserRepository", lambda *_a, **_k: user_repo)
    monkeypatch.setattr(
        "src.repositories.hh_linked_account.HhLinkedAccountRepository",
        lambda *_a, **_k: hh_repo,
    )
    monkeypatch.setattr(
        "src.repositories.work_experience.WorkExperienceRepository",
        lambda *_a, **_k: we_repo,
    )
    monkeypatch.setattr(
        "src.worker.tasks.autorespond._load_candidates",
        AsyncMock(return_value=[_vac(vid=101, hh_id="a")]),
    )
    monkeypatch.setattr(
        "src.worker.tasks.autorespond._regenerate_missing_compatibility_scores",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "src.worker.tasks.autorespond._run_negotiations_sync_with_retry",
        AsyncMock(return_value={"status": "ok"}),
    )
    import src.bot.modules.autoparse.services as _ap_services_mod

    monkeypatch.setattr(
        _ap_services_mod,
        "get_user_autoparse_settings",
        AsyncMock(return_value={"cover_letter_style": "professional"}),
    )

    progress = MagicMock()
    for method in (
        "set_nested_step_state",
        "set_step_state",
        "set_active_step_index",
        "set_nested_active_step_index",
        "set_nested_steps",
        "clear_nested_steps",
        "update_bar",
        "update_footer",
        "finish_task",
        "cancel_task",
    ):
        setattr(progress, method, AsyncMock())
    progress_bot = MagicMock()
    progress_bot.session.close = AsyncMock()
    monkeypatch.setattr(
        "src.worker.tasks.autorespond._start_or_update_progress_bar",
        AsyncMock(return_value=(progress, "autorespond:11:tid", progress_bot, 0, False)),
    )

    # 0 slots remaining → dispatcher must short-circuit with "rate_limited".
    monkeypatch.setattr(
        "src.worker.tasks.autorespond.remaining_ui_apply_slots_sync",
        lambda *_a, **_k: 0,
    )
    monkeypatch.setattr(
        "src.worker.tasks.autorespond.current_ui_apply_count_sync",
        lambda *_a, **_k: 50,
    )
    monkeypatch.setattr(
        "src.worker.tasks.autorespond.get_hh_ui_apply_max_per_day_effective",
        lambda: 50,
    )

    import src.worker.tasks.hh_ui_apply as _hh_ui_mod

    pump_delay = MagicMock()
    monkeypatch.setattr(_hh_ui_mod, "apply_pump_task", MagicMock(delay=pump_delay))

    with patch("src.worker.tasks.autorespond.settings") as mock_settings:
        mock_settings.hh_ui_apply_enabled = True
        mock_settings.autorespond_progress_tick_timeout_seconds = 5

        from src.worker.tasks.autorespond import _run_autorespond_async

        result = await _run_autorespond_async(
            session_factory,
            celery_task=MagicMock(create_bot=MagicMock(return_value=MagicMock())),
            company_id=11,
            vacancy_ids=None,
            trigger="manual",
            task_started_at=None,
        )

    assert result["status"] == "rate_limited"
    pump_delay.assert_not_called()
