import asyncio

from src.core.logging import get_logger, setup_logging

logger = get_logger(__name__)


async def _load_db_settings() -> None:
    from src.core.db_managed_settings import load_managed_settings_to_runtime

    await load_managed_settings_to_runtime()


async def main() -> None:
    setup_logging()
    logger.info("Starting HH Bot...")

    from src.bot.create import create_bot, create_dispatcher
    from src.db.engine import init_db

    await init_db()
    await _load_db_settings()
    logger.info("DB-managed settings loaded")

    from src.services.task_restart import (
        resume_hh_ui_batches_from_checkpoints,
        restart_pending_parsing_tasks,
    )

    enqueued = await restart_pending_parsing_tasks()
    if enqueued:
        logger.info("Restarted pending parsing tasks", count=enqueued)

    hh_ui_resumed = await resume_hh_ui_batches_from_checkpoints()
    if hh_ui_resumed:
        logger.info("Resumed HH UI batch checkpoints", count=hh_ui_resumed)

    bot = create_bot()
    dp = create_dispatcher()

    from src.services.progress_service import refresh_progress_pins_for_active_chats

    await refresh_progress_pins_for_active_chats(bot)

    logger.info("Bot is polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
