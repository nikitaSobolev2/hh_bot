import asyncio

from src.core.logging import get_logger, setup_logging

logger = get_logger(__name__)


async def main() -> None:
    setup_logging()
    logger.info("Starting HH Bot...")

    from src.bot.create import create_bot, create_dispatcher
    from src.db.engine import init_db

    await init_db()

    bot = create_bot()
    dp = create_dispatcher()

    logger.info("Bot is polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
