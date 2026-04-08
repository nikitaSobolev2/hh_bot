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
    from src.services.bot_pin_cleanup import run_startup_bot_pin_cleanup
    from src.services.progress_service import refresh_progress_pins_for_active_chats
    from src.services.task_restart import (
        restart_pending_parsing_tasks,
        resume_hh_ui_batches_from_checkpoints,
    )

    await init_db()
    await _load_db_settings()
    logger.info("DB-managed settings loaded")

    bot = create_bot()
    dp = create_dispatcher()
    me = await bot.get_me()

    await run_startup_bot_pin_cleanup(bot, bot_id=me.id)

    await refresh_progress_pins_for_active_chats(bot)

    enqueued = await restart_pending_parsing_tasks()
    if enqueued:
        logger.info("Restarted pending parsing tasks", count=enqueued)

    hh_ui_resumed = await resume_hh_ui_batches_from_checkpoints()
    if hh_ui_resumed:
        logger.info("Resumed HH UI batch checkpoints", count=hh_ui_resumed)

    logger.info("Bot is polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
