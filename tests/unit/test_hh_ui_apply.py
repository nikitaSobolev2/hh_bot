import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_apply_batch_ui_missing_browser_session_finalizes_every_item() -> None:
    task = MagicMock()
    bot = MagicMock()
    bot.session.close = AsyncMock()
    task.create_bot.return_value = bot

    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session_factory = MagicMock(return_value=session)

    acc_repo = MagicMock()
    acc_repo.get_by_id = AsyncMock(return_value=None)

    items = [
        {
            "autoparsed_vacancy_id": 1,
            "hh_vacancy_id": "100",
            "resume_id": "r1",
            "vacancy_url": "https://hh.ru/vacancy/100",
        },
        {
            "autoparsed_vacancy_id": 2,
            "hh_vacancy_id": "200",
            "resume_id": "r2",
            "vacancy_url": "https://hh.ru/vacancy/200",
        },
    ]
    autorespond_progress = {
        "task_key": "taskgroup:abc",
        "total": 2,
        "locale": "en",
        "title": "Batch",
        "celery_task_id": "parent-id",
        "finish_progress_task": False,
    }

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
        patch(
            "src.worker.tasks.hh_ui_apply.HhLinkedAccountRepository",
            return_value=acc_repo,
        ),
        patch(
            "src.worker.tasks.hh_ui_apply.HhTokenCipher",
            return_value=MagicMock(),
        ),
        patch(
            "src.services.autorespond_progress.is_autorespond_cancelled_sync",
            return_value=False,
        ),
        patch(
            "src.services.autorespond_progress.save_hh_ui_batch_checkpoint_sync",
        ),
        patch(
            "src.worker.tasks.hh_ui_apply._finalize_batch_item_async",
            new_callable=AsyncMock,
        ) as mock_finalize,
    ):
        from src.worker.tasks.hh_ui_apply import _apply_batch_ui_async

        result = await _apply_batch_ui_async(
            task,
            session_factory,
            user_id=11,
            chat_id=22,
            message_id=0,
            locale="en",
            hh_linked_account_id=33,
            feed_session_id=0,
            items=items,
            cover_letter_style="professional",
            cover_task_enabled=True,
            silent_feed=True,
            autorespond_progress=autorespond_progress,
        )

    assert result == {"status": "error", "reason": "no_browser_session"}
    assert mock_finalize.await_count == len(items)
