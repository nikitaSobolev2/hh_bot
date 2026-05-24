"""Unit tests for autorespond backlog scoring."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _vac(*, vid: int, hh_id: str = "123", score: float | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=vid,
        hh_vacancy_id=hh_id,
        compatibility_score=score,
        title="Python Dev",
        description="" if score is None else "Backend role",
        raw_skills=[],
        url=f"https://hh.ru/vacancy/{hh_id}",
        autoparse_company_id=1,
        ai_summary=None,
        ai_stack=None,
        needs_employer_questions=False,
        company_name="ACME",
        company_url=None,
        salary=None,
        tags=None,
    )


def test_vacancy_needs_detail_parse_true_when_description_missing() -> None:
    from src.services.autorespond_backlog import vacancy_needs_detail_parse

    assert vacancy_needs_detail_parse(_vac(vid=1, score=None)) is True


def test_vacancy_needs_detail_parse_false_when_description_present() -> None:
    from src.services.autorespond_backlog import vacancy_needs_detail_parse

    assert vacancy_needs_detail_parse(_vac(vid=1, score=80.0)) is False


@pytest.mark.asyncio
async def test_score_pending_vacancies_persists_ai_result() -> None:
    from src.services.autorespond_backlog import score_pending_vacancies

    vacancy = _vac(vid=7, hh_id="777", score=None)
    vacancy.description = "Python backend role"
    updated = SimpleNamespace(
        id=7,
        compatibility_score=82.0,
        ai_summary="Good fit",
        ai_stack=["Python"],
    )
    session_factory = MagicMock()
    session = AsyncMock()
    session_factory.return_value.__aenter__.return_value = session
    repo = MagicMock()
    repo.get_analyzed_for_user_hh_id = AsyncMock(return_value=None)
    repo.get_by_id = AsyncMock(return_value=updated)
    repo.update = AsyncMock()

    analysis = SimpleNamespace(compatibility_score=82.0, summary="Good fit", stack=["Python"])

    with (
        patch(
            "src.services.autorespond_backlog.AutoparsedVacancyRepository",
            return_value=repo,
        ),
        patch(
            "src.services.autorespond_backlog._detail_parse_vacancies",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "src.services.autorespond_backlog.build_vacancy_api_context_from_orm",
            return_value=None,
        ),
        patch("src.services.autorespond_backlog.AIClient") as ai_cls,
        patch(
            "src.services.autorespond_backlog.close_ai_client",
            new=AsyncMock(),
        ),
        patch(
            "src.services.autorespond_backlog.get_system_load_guard",
            return_value=MagicMock(wait_if_overloaded=AsyncMock()),
        ),
    ):
        ai_cls.return_value.analyze_vacancies_batch = AsyncMock(return_value={"777": analysis})
        scored = await score_pending_vacancies(
            session_factory,
            company_id=1,
            user_id=3,
            vacancies=[vacancy],
            user_stack=["Python"],
            user_exp="5 years backend",
            parse_mode="api",
            detail_parse_mode="api",
            web_storage=None,
        )

    assert len(scored) == 1
    repo.update.assert_awaited()
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_bootstrap_pending_scores_unscored_before_enqueue() -> None:
    from src.services.autorespond_streaming import (
        StreamingAutorespondContext,
        StreamingAutorespondFeed,
    )

    unscored = _vac(vid=42, hh_id="42", score=None)
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
        parse_mode="api",
        parse_hh_linked_account_id=1,
    )
    feed._resume_items = [{"id": "r1"}]
    feed._cover_task_enabled = True

    scored = _vac(vid=42, hh_id="42", score=80.0)
    scored.description = "Python backend"
    score_mock = AsyncMock(return_value=[scored])

    with (
        patch.object(feed, "_load_company_context", new=AsyncMock(return_value=True)),
        patch(
            "src.worker.tasks.autorespond._pending_autorespond_autoparsed_vacancy_ids",
            new=AsyncMock(return_value=[42]),
        ),
        patch(
            "src.services.autorespond_streaming.AutoparsedVacancyRepository",
        ) as repo_cls,
        patch.object(feed, "_already_handled", new=AsyncMock(return_value=set())),
        patch.object(feed, "_score_unscored_pending", score_mock),
        patch.object(feed, "_enqueue_vacancy", new=AsyncMock(return_value=True)) as enqueue,
    ):
        repo = repo_cls.return_value
        repo.get_by_ids_for_company = AsyncMock(return_value=[unscored])
        enqueued = await feed.bootstrap_pending_from_db()

    score_mock.assert_awaited_once_with([unscored])
    enqueue.assert_awaited_once_with(scored, already_handled=set())
    assert enqueued == 1
