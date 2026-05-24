"""HH UI apply attempt persistence edge cases."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from src.services.hh_ui.outcomes import ApplyOutcome, ApplyResult
from src.worker.tasks import hh_ui_apply as mod


@pytest.mark.asyncio
async def test_persist_ui_apply_attempt_skips_when_vacancy_row_missing() -> None:
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    vac_repo = MagicMock()
    vac_repo.get_by_id = AsyncMock(return_value=None)
    attempt_repo = MagicMock()
    attempt_repo.create = AsyncMock()

    session_factory = MagicMock(return_value=session)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "src.repositories.autoparse.AutoparsedVacancyRepository",
            lambda _s: vac_repo,
        )
        mp.setattr(mod, "HhApplicationAttemptRepository", lambda _s: attempt_repo)
        result = await mod._persist_ui_apply_attempt_and_feed_effects(
            session_factory=session_factory,
            user_id=1,
            hh_linked_account_id=2,
            autoparsed_vacancy_id=2634,
            hh_vacancy_id="133264985",
            resume_id="resume-hash",
            feed_session_id=0,
            result=ApplyResult(outcome=ApplyOutcome.ERROR, detail="popup_api:letter-required"),
        )

    assert result[0] == "error"
    attempt_repo.create.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_persist_ui_apply_attempt_swallows_fk_integrity_error() -> None:
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    vacancy = MagicMock()
    vac_repo = MagicMock()
    vac_repo.get_by_id = AsyncMock(return_value=vacancy)
    vac_repo.update = AsyncMock()

    attempt_repo = MagicMock()
    attempt_repo.create = AsyncMock(
        side_effect=IntegrityError("insert", {}, Exception("fk violation"))
    )

    session_factory = MagicMock(return_value=session)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "src.repositories.autoparse.AutoparsedVacancyRepository",
            lambda _s: vac_repo,
        )
        mp.setattr(mod, "HhApplicationAttemptRepository", lambda _s: attempt_repo)
        result = await mod._persist_ui_apply_attempt_and_feed_effects(
            session_factory=session_factory,
            user_id=1,
            hh_linked_account_id=2,
            autoparsed_vacancy_id=2634,
            hh_vacancy_id="133264985",
            resume_id="resume-hash",
            feed_session_id=0,
            result=ApplyResult(outcome=ApplyOutcome.ERROR, detail="popup_api:letter-required"),
        )

    assert result[0] == "error"
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
