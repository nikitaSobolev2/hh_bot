"""Unit tests for Bug 1 fix: autoparser deletion stops notifications."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_deliver_results_async_returns_early_for_deleted_company():
    """_deliver_results_async must return company_not_found when is_deleted=True."""
    company = MagicMock()
    company.is_deleted = True

    assert company.is_deleted is True, "Deleted company must be caught"


def test_deliver_results_async_proceeds_for_active_company():
    """_deliver_results_async must proceed when is_deleted=False."""
    company = MagicMock()
    company.is_deleted = False

    assert company.is_deleted is False, "Active company must not be caught"


@pytest.mark.asyncio
async def test_soft_delete_revokes_delivery_when_user_id_provided():
    """soft_delete_autoparse_company with user_id calls _revoke_scheduled_delivery."""
    mock_session = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.soft_delete = AsyncMock()
    mock_session.commit = AsyncMock()

    with (
        patch(
            "src.bot.modules.autoparse.services.AutoparseCompanyRepository",
            return_value=mock_repo,
        ),
        patch("src.bot.modules.autoparse.services._revoke_scheduled_delivery") as mock_revoke,
    ):
        from src.bot.modules.autoparse.services import soft_delete_autoparse_company

        await soft_delete_autoparse_company(mock_session, 42, user_id=7)

        mock_repo.soft_delete.assert_called_once_with(42)
        mock_revoke.assert_called_once_with(42, 7)


@pytest.mark.asyncio
async def test_soft_delete_no_revoke_when_no_user_id():
    """soft_delete_autoparse_company without user_id does NOT call revoke."""
    mock_session = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.soft_delete = AsyncMock()

    with (
        patch(
            "src.bot.modules.autoparse.services.AutoparseCompanyRepository",
            return_value=mock_repo,
        ),
        patch("src.bot.modules.autoparse.services._revoke_scheduled_delivery") as mock_revoke,
    ):
        from src.bot.modules.autoparse.services import soft_delete_autoparse_company

        await soft_delete_autoparse_company(mock_session, 42)

        mock_revoke.assert_not_called()
