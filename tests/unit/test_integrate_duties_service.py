"""Unit tests for parsing integrate duties service helpers."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.modules.parsing.services import apply_integrated_duties, get_top_keywords


class _Agg:
    def __init__(self, top_keywords):
        self.top_keywords = top_keywords


def test_get_top_keywords_returns_top_25_by_frequency():
    keywords = {f"kw{i}": i for i in range(30)}
    agg = _Agg(keywords)

    result = get_top_keywords(agg, top_n=25)

    assert len(result) == 25
    assert result[0] == "kw29"
    assert result[-1] == "kw5"


@pytest.mark.asyncio
async def test_apply_integrated_duties_updates_owned_work_experience():
    owned = MagicMock()
    owned.user_id = 7
    owned.is_active = True
    owned.duties = "- Old duty"

    session = MagicMock()
    session.commit = AsyncMock()

    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=owned)

    payload = {
        "work_experiences": [
            {
                "work_exp_id": 42,
                "duties": ["New duty with Django", "Reviewed pull requests"],
            }
        ]
    }

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "src.bot.modules.parsing.services.WorkExperienceRepository",
            lambda _session: repo,
        )
        updated = await apply_integrated_duties(session, 7, payload)

    assert updated == 1
    assert "- New duty with Django" in owned.duties
    assert "- Reviewed pull requests" in owned.duties
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_apply_integrated_duties_skips_foreign_work_experience():
    foreign = MagicMock()
    foreign.user_id = 99
    foreign.is_active = True
    foreign.duties = "- Keep"

    session = MagicMock()
    session.commit = AsyncMock()

    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=foreign)

    payload = {
        "work_experiences": [
            {"work_exp_id": 42, "duties": ["Should not apply"]},
        ]
    }

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "src.bot.modules.parsing.services.WorkExperienceRepository",
            lambda _session: repo,
        )
        updated = await apply_integrated_duties(session, 7, payload)

    assert updated == 0
    assert foreign.duties == "- Keep"
    session.commit.assert_not_awaited()
