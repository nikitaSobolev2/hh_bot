import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from src.core.logging import get_logger
from src.db.engine import async_session_factory
from src.models.user import User
from src.repositories.user import UserRepository

logger = get_logger(__name__)


class AuthMiddleware(BaseMiddleware):
    """Find or create the user on every update and inject into handler data."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)

        tg_user = _extract_tg_user(event)
        if tg_user is None:
            return await handler(event, data)

        async with async_session_factory() as session:
            repo = UserRepository(session)
            user = await repo.get_by_telegram_id(tg_user.id)

            if user is None:
                from sqlalchemy import select

                from src.models.role import Role

                stmt = select(Role).where(Role.name == "user")
                result = await session.execute(stmt)
                role = result.scalar_one_or_none()
                if role is None:
                    logger.error("Default 'user' role not found — run seed_roles.py first")
                    return await handler(event, data)

                user = User(
                    telegram_id=tg_user.id,
                    username=tg_user.username or "",
                    first_name=tg_user.first_name or "",
                    last_name=tg_user.last_name or "",
                    language_code=tg_user.language_code or "ru",
                    role_id=role.id,
                    referral_code=uuid.uuid4().hex[:12],
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                logger.info("New user registered", telegram_id=tg_user.id)
            else:
                if tg_user.username and tg_user.username != user.username:
                    user.username = tg_user.username
                    await session.commit()

            if user.is_banned:
                logger.info("Blocked request from banned user", telegram_id=tg_user.id)
                if event.message:
                    await event.message.answer("Your account has been suspended.")
                elif event.callback_query:
                    await event.callback_query.answer(
                        "Your account has been suspended.", show_alert=True
                    )
                return None

            data["user"] = user
            data["session"] = session
            return await handler(event, data)


def _extract_tg_user(update: Update):
    if update.message and update.message.from_user:
        return update.message.from_user
    if update.callback_query and update.callback_query.from_user:
        return update.callback_query.from_user
    if update.inline_query and update.inline_query.from_user:
        return update.inline_query.from_user
    return None
