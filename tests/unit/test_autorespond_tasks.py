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
