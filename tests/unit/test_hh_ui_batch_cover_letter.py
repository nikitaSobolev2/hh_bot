"""Cover letter timeout behavior inside hh_ui batch apply."""

from __future__ import annotations

import asyncio
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.hh.vacancy_public import HhVacancyPublicPreflight


@pytest.mark.asyncio
async def test_batch_cover_letter_timeout_applies_without_letter() -> None:
    task = MagicMock()
    bot = MagicMock()
    bot.session.close = AsyncMock()
    task.create_bot.return_value = bot

    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session_factory = MagicMock(return_value=session)

    acc = MagicMock()
    acc.browser_storage_enc = b"enc"
    acc_repo = MagicMock()
    acc_repo.get_by_id = AsyncMock(return_value=acc)

    settings_repo = MagicMock()
    settings_repo.get_value = AsyncMock(return_value=False)

    items = [
        {
            "autoparsed_vacancy_id": 10,
            "hh_vacancy_id": "100",
            "resume_id": "r1",
            "vacancy_url": "https://hh.ru/vacancy/100",
        },
    ]

    async def slow_cover(*args, **kwargs):
        await asyncio.sleep(60)
        return "never"

    captured_specs: list = []

    def fake_batch(**kwargs):
        captured_specs.extend(kwargs["items"])
        return ([], None)

    cryptography_mod = ModuleType("cryptography")
    fernet_mod = ModuleType("cryptography.fernet")
    fernet_mod.Fernet = MagicMock()
    fernet_mod.InvalidToken = Exception

    with (
        patch.dict(
            sys.modules,
            {
                "cryptography": cryptography_mod,
                "cryptography.fernet": fernet_mod,
            },
        ),
        patch("src.worker.tasks.hh_ui_apply.HhLinkedAccountRepository", return_value=acc_repo),
        patch("src.worker.tasks.hh_ui_apply.AppSettingRepository", return_value=settings_repo),
        patch("src.worker.tasks.hh_ui_apply.HhTokenCipher", return_value=MagicMock()),
        patch(
            "src.worker.tasks.hh_ui_apply.decrypt_browser_storage",
            return_value={"cookies": []},
        ),
        patch(
            "src.services.hh.vacancy_public.hh_vacancy_public_preflight",
            new_callable=AsyncMock,
            return_value=HhVacancyPublicPreflight(
                unavailable=False,
                requires_employer_test=False,
            ),
        ),
        patch(
            "src.worker.tasks.cover_letter.generate_cover_letter_plaintext_for_autoparsed_vacancy",
            side_effect=slow_cover,
        ),
        patch("src.worker.tasks.hh_ui_apply.apply_to_vacancies_ui_batch", side_effect=fake_batch),
        patch("src.worker.tasks.hh_ui_apply._finalize_batch_item_async", new_callable=AsyncMock),
        patch("src.worker.tasks.hh_ui_apply.settings") as mock_settings,
    ):
        mock_settings.hh_ui_batch_cover_letter_timeout_seconds = 0.05
        mock_settings.hh_ui_apply_max_retries = 1
        mock_settings.hh_ui_apply_retry_initial_seconds = 1.0
        mock_settings.hh_ui_apply_retry_delay_cap_seconds = 1.0
        mock_settings.hh_ui_debug_screenshot_dir = "/tmp"
        from src.worker.tasks.hh_ui_apply import _apply_batch_ui_async

        result = await _apply_batch_ui_async(
            task,
            session_factory,
            user_id=1,
            chat_id=2,
            message_id=0,
            locale="ru",
            hh_linked_account_id=1,
            feed_session_id=0,
            items=items,
            cover_letter_style="professional",
            cover_task_enabled=True,
            silent_feed=True,
            autorespond_progress=None,
        )

    assert result == {"status": "ok", "processed": 1}
    assert len(captured_specs) == 1
    assert captured_specs[0].cover_letter == ""


@pytest.mark.asyncio
async def test_generate_batch_cover_letter_bounded_returns_empty_on_timeout() -> None:
    async def slow_cover(*args, **kwargs):
        await asyncio.sleep(60)
        return "x"

    session_factory = MagicMock()
    with (
        patch(
            "src.worker.tasks.cover_letter.generate_cover_letter_plaintext_for_autoparsed_vacancy",
            side_effect=slow_cover,
        ),
        patch("src.worker.tasks.hh_ui_apply.settings") as mock_settings,
    ):
        mock_settings.hh_ui_batch_cover_letter_timeout_seconds = 0.05
        from src.worker.tasks.hh_ui_apply import _generate_batch_cover_letter_bounded

        letter, skipped = await _generate_batch_cover_letter_bounded(
            session_factory,
            user_id=1,
            vacancy_id=9,
            cover_letter_style="professional",
            cover_ai=MagicMock(),
        )
    assert letter == ""
    assert skipped is True
