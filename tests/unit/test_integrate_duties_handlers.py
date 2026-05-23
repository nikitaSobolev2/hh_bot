"""Unit tests for integrate duties handler validation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.modules.parsing.handlers import _validate_integrate_duties_prerequisites


@pytest.mark.asyncio
async def test_validate_integrate_duties_prerequisites_returns_error_without_keywords():
    session = MagicMock()
    user = MagicMock(id=1)
    i18n = MagicMock()
    i18n.get.return_value = "no keywords"

    company = MagicMock(status="completed")
    agg = MagicMock(top_keywords={})

    with patch(
        "src.bot.modules.parsing.handlers.parsing_service.get_company_for_user",
        new=AsyncMock(return_value=company),
    ), patch(
        "src.bot.modules.parsing.handlers.parsing_service.get_aggregated_result",
        new=AsyncMock(return_value=agg),
    ):
        _, _, error = await _validate_integrate_duties_prerequisites(session, user, 5, i18n)

    assert error == "no keywords"


@pytest.mark.asyncio
async def test_validate_integrate_duties_prerequisites_returns_error_without_duties():
    session = MagicMock()
    user = MagicMock(id=1)
    i18n = MagicMock()
    i18n.get.return_value = "no duties"

    company = MagicMock(status="completed")
    agg = MagicMock(top_keywords={"Python": 3})

    with patch(
        "src.bot.modules.parsing.handlers.parsing_service.get_company_for_user",
        new=AsyncMock(return_value=company),
    ), patch(
        "src.bot.modules.parsing.handlers.parsing_service.get_aggregated_result",
        new=AsyncMock(return_value=agg),
    ), patch(
        "src.bot.modules.parsing.handlers.parsing_service.get_work_experiences_with_duties",
        new=AsyncMock(return_value=[]),
    ):
        _, _, error = await _validate_integrate_duties_prerequisites(session, user, 5, i18n)

    assert error == "no duties"
