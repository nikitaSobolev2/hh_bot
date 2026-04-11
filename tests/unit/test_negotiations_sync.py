from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.parser.scraper import HHCaptchaRequiredError


def _make_session_factory(session: MagicMock):
    @asynccontextmanager
    async def factory():
        yield session

    return factory


@pytest.mark.asyncio
async def test_fetch_merged_vac_dicts_abort_remaining_requests_on_captcha():
    from src.services.autoparse.negotiations_vacancy_import import fetch_merged_vac_dicts_for_hh_ids

    parsed_urls: list[str] = []

    async def fake_parse_vacancy_page(self, client, url):
        parsed_urls.append(url)
        raise HHCaptchaRequiredError("HH public API circuit open (captcha cooldown)")

    with patch(
        "src.services.autoparse.negotiations_vacancy_import.HHScraper.parse_vacancy_page",
        new=fake_parse_vacancy_page,
    ):
        with pytest.raises(HHCaptchaRequiredError):
            await fetch_merged_vac_dicts_for_hh_ids(["1", "2", "3"], concurrency=1)

    assert parsed_urls == ["https://hh.ru/vacancy/1"]


@pytest.mark.asyncio
async def test_sync_negotiations_returns_error_on_captcha_abort():
    from src.worker.tasks.negotiations_sync import _sync_negotiations_async

    session = MagicMock()
    acc = SimpleNamespace(id=9, user_id=42, browser_storage_enc="enc")
    company = SimpleNamespace(id=16, user_id=42)

    acc_repo = MagicMock()
    acc_repo.get_by_id = AsyncMock(return_value=acc)

    company_repo = MagicMock()
    company_repo.get_by_id = AsyncMock(return_value=company)

    vac_repo = MagicMock()
    vac_repo.hh_vacancy_ids_already_in_company = AsyncMock(return_value=set())

    with (
        patch(
            "src.worker.tasks.negotiations_sync.HhLinkedAccountRepository",
            return_value=acc_repo,
        ),
        patch(
            "src.worker.tasks.negotiations_sync.AutoparseCompanyRepository",
            return_value=company_repo,
        ),
        patch(
            "src.worker.tasks.negotiations_sync.AutoparsedVacancyRepository",
            return_value=vac_repo,
        ),
        patch("src.worker.tasks.negotiations_sync.HhTokenCipher", return_value=MagicMock()),
        patch(
            "src.worker.tasks.negotiations_sync.decrypt_browser_storage",
            return_value={"cookies": []},
        ),
        patch(
            "src.worker.tasks.negotiations_sync.asyncio.to_thread",
            new=AsyncMock(return_value=({"vac-1", "vac-2"}, None)),
        ),
        patch(
            "src.services.autoparse.negotiations_vacancy_import.fetch_merged_vac_dicts_for_hh_ids",
            new=AsyncMock(
                side_effect=HHCaptchaRequiredError("HH public API circuit open (captcha cooldown)")
            ),
        ),
    ):
        result = await _sync_negotiations_async(
            _make_session_factory(session),
            task=None,
            user_id=42,
            hh_linked_account_id=9,
            autoparse_company_id=16,
            chat_id=0,
            locale="ru",
            notify_user=False,
        )

    assert result == {"status": "error", "reason": "captcha_required"}
