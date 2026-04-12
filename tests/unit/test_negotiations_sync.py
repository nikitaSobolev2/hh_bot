from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

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

    settings_repo = MagicMock()
    settings_repo.get_value = AsyncMock(return_value=True)

    vac_repo = MagicMock()
    vac_repo.hh_vacancy_ids_already_in_company = AsyncMock(return_value=set())

    with (
        patch(
            "src.worker.tasks.negotiations_sync.AppSettingRepository",
            return_value=settings_repo,
        ),
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

    assert result == {
        "status": "error",
        "reason": "captcha_required",
        "vacancy_ids": ["vac-1", "vac-2"],
    }


@pytest.mark.asyncio
async def test_sync_negotiations_html_only_uses_basic_cards_without_vacancy_details():
    from src.worker.tasks.negotiations_sync import _sync_negotiations_async

    session = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            SimpleNamespace(scalar_one_or_none=lambda: None),
            SimpleNamespace(scalar_one_or_none=lambda: None),
            SimpleNamespace(all=lambda: [("vac-1", 101), ("vac-2", 102)]),
        ]
    )
    acc = SimpleNamespace(id=9, user_id=42, browser_storage_enc="enc")
    company = SimpleNamespace(id=16, user_id=42)

    settings_repo = MagicMock()
    settings_repo.get_value = AsyncMock(return_value=False)

    acc_repo = MagicMock()
    acc_repo.get_by_id = AsyncMock(return_value=acc)

    company_repo = MagicMock()
    company_repo.get_by_id = AsyncMock(return_value=company)

    vac_repo = MagicMock()
    vac_repo.hh_vacancy_ids_already_in_company = AsyncMock(return_value=set())
    vac_repo.list_ids_by_company_and_hh_vacancy_ids = AsyncMock(return_value=[101, 102])

    attempt_repo = MagicMock()
    attempt_repo.user_has_any_attempt_for_hh_vacancy = AsyncMock(side_effect=[False, False])
    attempt_repo.create = AsyncMock()

    feed_repo = MagicMock()
    feed_repo.list_sessions_for_user_company = AsyncMock(return_value=[])

    built_rows = [SimpleNamespace(id=101), SimpleNamespace(id=102)]
    basic_cards = {
        "vac-1": {
            "hh_vacancy_id": "vac-1",
            "url": "https://hh.ru/vacancy/vac-1",
            "title": "Backend Developer",
            "company_name": "Acme",
            "company_url": "https://hh.ru/employer/1",
        },
        "vac-2": {
            "hh_vacancy_id": "vac-2",
            "url": "https://hh.ru/vacancy/vac-2",
            "title": "Python Engineer",
            "company_name": "Beta",
            "company_url": "https://hh.ru/employer/2",
        },
    }

    with (
        patch(
            "src.worker.tasks.negotiations_sync.AppSettingRepository",
            return_value=settings_repo,
        ),
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
        patch(
            "src.worker.tasks.negotiations_sync.HhApplicationAttemptRepository",
            return_value=attempt_repo,
        ),
        patch(
            "src.worker.tasks.negotiations_sync.VacancyFeedSessionRepository",
            return_value=feed_repo,
        ),
        patch("src.worker.tasks.negotiations_sync.HHEmployerRepository", return_value=MagicMock()),
        patch("src.worker.tasks.negotiations_sync.HHAreaRepository", return_value=MagicMock()),
        patch("src.worker.tasks.negotiations_sync.HhTokenCipher", return_value=MagicMock()),
        patch(
            "src.worker.tasks.negotiations_sync.decrypt_browser_storage",
            return_value={"cookies": []},
        ),
        patch(
            "src.worker.tasks.negotiations_sync.asyncio.to_thread",
            new=AsyncMock(return_value=(basic_cards, {"vac-1", "vac-2"}, None)),
        ),
        patch(
            "src.worker.tasks.autoparse._build_autoparsed_vacancy",
            side_effect=built_rows,
        ) as build_mock,
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

    assert result["status"] == "ok"
    assert result["vacancies_imported"] == 2
    assert build_mock.call_count == 2
    assert build_mock.call_args_list[0].args[0]["title"] == "Backend Developer"
    assert build_mock.call_args_list[0].args[0]["company_name"] == "Acme"
    assert build_mock.call_args_list[1].args[0]["title"] == "Python Engineer"
    assert build_mock.call_args_list[1].args[0]["company_name"] == "Beta"
    attempt_repo.create.assert_awaited()
    assert attempt_repo.user_has_any_attempt_for_hh_vacancy.await_args_list == [
        call(42, 9, "vac-1"),
        call(42, 9, "vac-2"),
    ]
