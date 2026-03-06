from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from src.models.user import User


class LocaleMiddleware(BaseMiddleware):
    """Injects the user's language_code as 'locale' for i18n resolution."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("user")
        if user is not None:
            data["locale"] = user.language_code or "ru"
        else:
            data["locale"] = "ru"

        return await handler(event, data)
