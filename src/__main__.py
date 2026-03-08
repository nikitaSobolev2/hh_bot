import asyncio

from src.core.logging import get_logger, setup_logging

logger = get_logger(__name__)


async def _load_db_settings() -> None:
    from src.bot.modules.admin.keyboards import MANAGED_SETTINGS
    from src.config import sync_setting_to_runtime
    from src.db.engine import async_session_factory
    from src.repositories.app_settings import AppSettingRepository

    async with async_session_factory() as session:
        repo = AppSettingRepository(session)
        for key, _, _ in MANAGED_SETTINGS:
            val = await repo.get_value(key)
            if val is not None:
                sync_setting_to_runtime(key, val)


async def main() -> None:
    setup_logging()
    logger.info("Starting HH Bot...")

    from src.bot.create import create_bot, create_dispatcher
    from src.db.engine import init_db

    await init_db()
    await _load_db_settings()
    logger.info("DB-managed settings loaded")

    bot = create_bot()
    dp = create_dispatcher()

    logger.info("Bot is polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
