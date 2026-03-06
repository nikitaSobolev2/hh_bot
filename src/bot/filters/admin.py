from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, TelegramObject

from src.models.user import User


class AdminFilter(BaseFilter):
    async def __call__(self, event: TelegramObject, user: User) -> bool:
        if not user.is_admin:
            if isinstance(event, CallbackQuery):
                await event.answer("Access denied", show_alert=True)
            return False
        return True
