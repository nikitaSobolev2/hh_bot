from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from src.config import settings


def create_bot() -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    storage = RedisStorage.from_url(settings.redis_url)
    dp = Dispatcher(storage=storage)
    _register_middlewares(dp)
    _register_routers(dp)
    return dp


def _register_middlewares(dp: Dispatcher) -> None:
    from src.bot.middlewares.auth import AuthMiddleware
    from src.bot.middlewares.i18n import LocaleMiddleware
    from src.bot.middlewares.throttle import ThrottleMiddleware
    from src.core.i18n import setup_i18n

    dp.update.middleware(ThrottleMiddleware())
    dp.update.middleware(AuthMiddleware())
    dp.update.middleware(LocaleMiddleware())
    setup_i18n(dp)


def _register_routers(dp: Dispatcher) -> None:
    from src.bot.modules.admin.handlers import router as admin_router
    from src.bot.modules.parsing.handlers import router as parsing_router
    from src.bot.modules.profile.handlers import router as profile_router
    from src.bot.modules.start.handlers import router as start_router
    from src.bot.modules.support.admin_handlers import router as support_admin_router
    from src.bot.modules.support.user_handlers import router as support_user_router
    from src.bot.modules.user_settings.handlers import router as user_settings_router

    dp.include_router(start_router)
    dp.include_router(profile_router)
    dp.include_router(user_settings_router)
    dp.include_router(parsing_router)
    dp.include_router(support_user_router)
    dp.include_router(support_admin_router)
    dp.include_router(admin_router)
