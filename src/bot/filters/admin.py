from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, TelegramObject

from src.core.i18n import get_text
from src.models.user import User


class AdminFilter(BaseFilter):
    async def __call__(self, event: TelegramObject, user: User) -> bool:
        if not user.is_admin:
            if isinstance(event, CallbackQuery):
                locale = user.language_code or "ru"
                await event.answer(get_text("access-denied", locale), show_alert=True)
            return False
        return True
