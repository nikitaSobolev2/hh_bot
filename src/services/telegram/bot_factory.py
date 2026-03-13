"""Shared Telegram Bot factory for use in Celery tasks.

All tasks must use ``create_task_bot()`` instead of inlining Bot construction.
This ensures consistent parse mode and settings across all tasks.
"""

from __future__ import annotations


def create_task_bot() -> Bot:  # noqa: F821
    """Create an HTML-mode Bot instance using settings.bot_token.

    The caller is responsible for closing the session:

        bot = create_task_bot()
        try:
            await do_work(bot)
        finally:
            await bot.session.close()
    """
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    from src.config import settings

    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
