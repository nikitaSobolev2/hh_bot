import sys
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_session_factory(session: MagicMock):
    @asynccontextmanager
    async def factory():
        yield session

    return factory


def _stub_hh_modules():
    fake_token_service = MagicMock()
    fake_token_service.ensure_access_token = AsyncMock(return_value="token")
    fake_hh_client = MagicMock()
    fake_hh_client.HhApiClient = MagicMock()
    fake_hh_client.HhApiError = Exception
    fake_hh_client.apply_to_vacancy_with_resume = AsyncMock()
    fake_crypto = MagicMock()
    fake_crypto.HhTokenCipher = MagicMock()
    return patch.dict(
        "sys.modules",
        {
            "src.services.hh.token_service": fake_token_service,
            "src.services.hh.client": fake_hh_client,
            "src.services.hh.crypto": fake_crypto,
        },
    )


@pytest.mark.asyncio
async def test_regenerates_zero_compatibility_before_filtering():
    session = MagicMock()
    session.commit = AsyncMock()
    vacancy = SimpleNamespace(
        id=1,
        hh_vacancy_id="vac-1",
        title="Senior Backend Developer",
        description="Python Go Kafka",
        raw_skills=["Python", "Go"],
        compatibility_score=0.0,
        ai_summary=None,
        ai_stack=None,
    )

    async with _make_session_factory(session)() as _:
        pass

    repo = MagicMock()
    repo.update = AsyncMock()

    with _stub_hh_modules():
        from src.worker.tasks.autorespond import _regenerate_missing_compatibility_scores

        with (
            patch("src.repositories.autoparse.AutoparsedVacancyRepository", return_value=repo),
            patch(
                "src.services.ai.client.AIClient.analyze_vacancies_batch",
                new=AsyncMock(
                    return_value={
                        "vac-1": SimpleNamespace(
                            compatibility_score=78.0,
                            summary="Good fit",
                            stack=["Python", "Go"],
                        )
                    }
                ),
            ),
            patch(
                "src.schemas.vacancy.build_vacancy_api_context_from_orm",
                return_value=None,
            ),
        ):
            await _regenerate_missing_compatibility_scores(
                _make_session_factory(session),
                user_id=42,
                vacancies=[vacancy],
                user_stack=["Python", "Go"],
                user_exp="backend experience",
            )

    repo.update.assert_awaited_once()
    assert vacancy.compatibility_score == 78.0
    assert vacancy.ai_summary == "Good fit"
    assert vacancy.ai_stack == ["Python", "Go"]
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_disables_keyword_filter_during_autorespond_when_company_toggle_is_off():
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.commit = AsyncMock()

    company = SimpleNamespace(
        id=7,
        user_id=42,
        is_deleted=False,
        autorespond_enabled=True,
        autorespond_hh_linked_account_id=55,
        vacancy_title="Backend",
        keyword_filter="python",
        keyword_check_enabled=False,
        autorespond_min_compat=60,
        autorespond_keyword_mode="title_only",
        autorespond_max_per_run=20,
    )
    user = SimpleNamespace(id=42, language_code="ru", telegram_id=0)
    hh_linked = SimpleNamespace(resume_list_cache=[{"id": "resume-1"}])

    settings_repo = MagicMock()
    settings_repo.get_value = AsyncMock(return_value=True)

    company_repo = MagicMock()
    company_repo.get_by_id = AsyncMock(return_value=company)

    user_repo = MagicMock()
    user_repo.get_by_id = AsyncMock(return_value=user)

    hh_repo = MagicMock()
    hh_repo.get_by_id = AsyncMock(return_value=hh_linked)

    attempt_repo = MagicMock()
    attempt_repo.hh_vacancy_ids_with_success_or_employer_questions = AsyncMock(return_value=set())

    sys.modules.pop("src.worker.tasks.autorespond", None)

    with _stub_hh_modules():
        from src.worker.tasks import autorespond as autorespond_module

        with (
            patch.object(autorespond_module, "AppSettingRepository", return_value=settings_repo),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch(
                "src.repositories.hh_linked_account.HhLinkedAccountRepository",
                return_value=hh_repo,
            ),
            patch.object(
                autorespond_module,
                "HhApplicationAttemptRepository",
                return_value=attempt_repo,
            ),
            patch(
                "src.bot.modules.autoparse.services.get_user_autoparse_settings",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "src.repositories.work_experience.WorkExperienceRepository.get_active_by_user",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                autorespond_module,
                "_sync_negotiations_async",
                new=AsyncMock(
                    return_value={
                        "status": "ok",
                        "inserted": 0,
                        "skipped_existing": 0,
                        "total_parsed": 0,
                        "vacancies_imported": 0,
                    }
                ),
            ),
            patch.object(
                autorespond_module,
                "_load_candidates",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "src.bot.modules.autoparse.autorespond_logic.filter_vacancies_for_autorespond",
                new=MagicMock(return_value=[]),
            ) as filter_mock,
            patch(
                "src.services.ai.resume_selection.normalize_hh_resume_cache_items",
                return_value=[{"id": "resume-1"}],
            ),
        ):
            result = await autorespond_module._run_autorespond_async(
                _make_session_factory(session),
                celery_task=None,
                company_id=company.id,
                vacancy_ids=None,
                trigger="manual",
                task_started_at=None,
                suppress_progress=True,
            )

    assert result["status"] == "ok"
    assert filter_mock.call_args.kwargs["company_keyword_filter"] == ""


@pytest.mark.asyncio
async def test_logs_average_and_histogram_compatibility_breakdown():
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.commit = AsyncMock()

    company = SimpleNamespace(
        id=8,
        user_id=42,
        is_deleted=False,
        autorespond_enabled=True,
        autorespond_hh_linked_account_id=55,
        vacancy_title="Backend",
        keyword_filter="python",
        keyword_check_enabled=False,
        autorespond_min_compat=50,
        autorespond_keyword_mode="title_only",
        autorespond_max_per_run=0,
    )
    user = SimpleNamespace(id=42, language_code="ru", telegram_id=0)
    hh_linked = SimpleNamespace(resume_list_cache=[{"id": "resume-1"}])
    raw_vacancies = [
        SimpleNamespace(
            id=1,
            hh_vacancy_id="vac-1",
            compatibility_score=20,
            title="One",
            description="",
            needs_employer_questions=False,
        ),
        SimpleNamespace(
            id=2,
            hh_vacancy_id="vac-2",
            compatibility_score=60,
            title="Two",
            description="",
            needs_employer_questions=False,
        ),
        SimpleNamespace(
            id=3,
            hh_vacancy_id="vac-3",
            compatibility_score=90,
            title="Three",
            description="",
            needs_employer_questions=False,
        ),
        SimpleNamespace(
            id=4,
            hh_vacancy_id="vac-4",
            compatibility_score=None,
            title="Four",
            description="",
            needs_employer_questions=False,
        ),
    ]
    filtered_vacancies = [raw_vacancies[1], raw_vacancies[2]]

    settings_repo = MagicMock()
    settings_repo.get_value = AsyncMock(return_value=True)

    company_repo = MagicMock()
    company_repo.get_by_id = AsyncMock(return_value=company)

    user_repo = MagicMock()
    user_repo.get_by_id = AsyncMock(return_value=user)

    hh_repo = MagicMock()
    hh_repo.get_by_id = AsyncMock(return_value=hh_linked)

    attempt_repo = MagicMock()
    attempt_repo.hh_vacancy_ids_with_success_or_employer_questions = AsyncMock(return_value=set())
    logger_mock = MagicMock()

    sys.modules.pop("src.worker.tasks.autorespond", None)

    with _stub_hh_modules():
        from src.worker.tasks import autorespond as autorespond_module

        with (
            patch.object(autorespond_module, "logger", logger_mock),
            patch.object(autorespond_module, "AppSettingRepository", return_value=settings_repo),
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch(
                "src.repositories.hh_linked_account.HhLinkedAccountRepository",
                return_value=hh_repo,
            ),
            patch.object(
                autorespond_module,
                "HhApplicationAttemptRepository",
                return_value=attempt_repo,
            ),
            patch(
                "src.bot.modules.autoparse.services.get_user_autoparse_settings",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "src.repositories.work_experience.WorkExperienceRepository.get_active_by_user",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                autorespond_module,
                "_sync_negotiations_async",
                new=AsyncMock(
                    return_value={
                        "status": "ok",
                        "inserted": 0,
                        "skipped_existing": 0,
                        "total_parsed": 0,
                        "vacancies_imported": 0,
                    }
                ),
            ),
            patch.object(
                autorespond_module,
                "_load_candidates",
                new=AsyncMock(return_value=raw_vacancies),
            ),
            patch(
                "src.bot.modules.autoparse.autorespond_logic.filter_vacancies_for_autorespond",
                new=MagicMock(return_value=filtered_vacancies),
            ),
            patch(
                "src.services.ai.resume_selection.normalize_hh_resume_cache_items",
                return_value=[{"id": "resume-1"}],
            ),
        ):
            result = await autorespond_module._run_autorespond_async(
                _make_session_factory(session),
                celery_task=None,
                company_id=company.id,
                vacancy_ids=[1, 2, 3, 4],
                trigger="manual_pipeline",
                task_started_at=None,
                suppress_progress=True,
            )

    assert result["status"] == "ok"
    breakdown_calls = [
        call for call in logger_mock.info.call_args_list if call.args[0] == "autorespond_selection_breakdown"
    ]
    assert len(breakdown_calls) == 1
    breakdown = breakdown_calls[0].kwargs
    assert breakdown["compatibility_avg_percent_raw"] == 56.67
    assert breakdown["compatibility_missing_raw"] == 1
    assert breakdown["compatibility_histogram_raw"] == {
        "0_24": 1,
        "25_49": 0,
        "50_74": 1,
        "75_100": 1,
    }
    assert breakdown["compatibility_avg_percent_filtered"] == 75.0
    assert breakdown["compatibility_missing_filtered"] == 0
    assert breakdown["compatibility_histogram_filtered"] == {
        "0_24": 0,
        "25_49": 0,
        "50_74": 1,
        "75_100": 1,
    }


def test_merge_manual_pipeline_vacancy_ids_deduplicates_and_orders_newest_first():
    sys.modules.pop("src.worker.tasks.autorespond", None)

    with _stub_hh_modules():
        from src.worker.tasks.autorespond import _merge_manual_pipeline_vacancy_ids

    assert _merge_manual_pipeline_vacancy_ids([205, 204, 203], [205, 204, 202, 201]) == [
        205,
        204,
        203,
        202,
        201,
    ]


@pytest.mark.asyncio
async def test_manual_pipeline_passes_new_and_old_unreacted_ids_to_autorespond():
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    company = SimpleNamespace(id=7, user_id=42, is_deleted=False, is_enabled=True)
    user = SimpleNamespace(id=42, language_code="ru", telegram_id=123456)

    company_repo = MagicMock()
    company_repo.get_by_id = AsyncMock(return_value=company)

    user_repo = MagicMock()
    user_repo.get_by_id = AsyncMock(return_value=user)

    progress_service = MagicMock()
    progress_service.start_task = AsyncMock()
    progress_service.set_step_state = AsyncMock()
    progress_service.set_active_step_index = AsyncMock()

    bot = MagicMock()
    bot.session.close = AsyncMock()

    task = MagicMock()
    task.request.id = "task-123"
    task.create_bot.return_value = bot

    sys.modules.pop("src.worker.tasks.autorespond", None)

    with _stub_hh_modules():
        from src.worker.tasks import autorespond as autorespond_module

        with (
            patch(
                "src.repositories.autoparse.AutoparseCompanyRepository",
                return_value=company_repo,
            ),
            patch("src.repositories.user.UserRepository", return_value=user_repo),
            patch("src.services.progress_service.ProgressService", return_value=progress_service),
            patch("src.services.progress_service.create_progress_redis", return_value=MagicMock()),
            patch("src.core.i18n.get_text", side_effect=lambda key, locale: key),
            patch(
                "src.worker.tasks.autoparse._run_autoparse_company_async",
                new=AsyncMock(
                    return_value={
                        "status": "completed",
                        "company_id": company.id,
                        "new_count": 3,
                        "new_vacancy_ids": [205, 204, 203],
                    }
                ),
            ),
            patch.object(
                autorespond_module,
                "_unreacted_autoparsed_vacancy_ids",
                new=AsyncMock(return_value=[205, 204, 202, 201]),
            ),
            patch.object(
                autorespond_module,
                "_run_autorespond_async",
                new=AsyncMock(return_value={"status": "ok"}),
            ) as run_autorespond_mock,
        ):
            result = await autorespond_module._run_manual_autoparse_autorespond_pipeline_async(
                _make_session_factory(session),
                task,
                company.id,
                user.id,
            )

    assert result == {"status": "ok"}
    assert run_autorespond_mock.await_args.args[3] == [205, 204, 203, 202, 201]
    assert run_autorespond_mock.await_args.args[4] == "manual_pipeline"
