"""Re-enqueue pending and processing tasks on bot startup.

When the bot restarts (e.g. via docker compose up -d --build), Celery workers
are killed and in-flight tasks are lost. This module finds ParsingCompany
records stuck in pending/processing and re-enqueues them so they resume
from their Redis checkpoint when available.
"""

from __future__ import annotations

from src.core.logging import get_logger
from src.db.engine import async_session_factory
from src.repositories.app_settings import AppSettingRepository
from src.repositories.parsing import ParsingCompanyRepository
from src.worker.tasks.parsing import run_parsing_company

logger = get_logger(__name__)


async def restart_pending_parsing_tasks() -> int:
    """Re-enqueue all ParsingCompany with status pending or processing.

    Returns the number of tasks enqueued. Skips when task_parsing_enabled
    is False. Uses run_celery_task to avoid blocking the event loop.
    """
    from src.core.celery_async import run_celery_task

    async with async_session_factory() as session:
        settings_repo = AppSettingRepository(session)
        enabled = await settings_repo.get_value("task_parsing_enabled", default=True)
        if not enabled:
            logger.info("Parsing task disabled, skipping restart of pending tasks")
            return 0

        company_repo = ParsingCompanyRepository(session)
        companies = await company_repo.get_pending_or_processing()

    enqueued = 0
    for company in companies:
        if not company.user:
            logger.warning(
                "Skipping parsing company with missing user",
                company_id=company.id,
                user_id=company.user_id,
            )
            continue

        await run_celery_task(
            run_parsing_company,
            company.id,
            company.user_id,
            include_blacklisted=False,
            telegram_chat_id=company.user.telegram_id,
        )
        enqueued += 1
        logger.info(
            "Re-enqueued parsing task",
            company_id=company.id,
            user_id=company.user_id,
        )

    return enqueued
