from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.modules.admin.keyboards import MANAGED_SETTINGS
from src.models.balance import BalanceTransaction
from src.models.user import User
from src.repositories.app_settings import AppSettingRepository
from src.repositories.user import UserRepository

USERS_PER_PAGE = 10

_SENSITIVE_KEYS = {"openai_api_key"}


def find_setting_meta(key: str) -> tuple[str, str, str] | None:
    for k, label, stype in MANAGED_SETTINGS:
        if k == key:
            return k, label, stype
    return None


def mask_if_sensitive(key: str, value: str) -> str:
    if key in _SENSITIVE_KEYS and len(value) > 8:
        return value[:4] + "****" + value[-4:]
    return value


def format_user_detail(target: User) -> str:
    return (
        f"<b>👤 User #{target.id}</b>\n\n"
        f"<b>Name:</b> {target.first_name} {target.last_name or ''}\n"
        f"<b>Username:</b> @{target.username or '—'}\n"
        f"<b>Telegram ID:</b> <code>{target.telegram_id}</code>\n"
        f"<b>Role:</b> {target.role.name}\n"
        f"<b>Balance:</b> {target.balance}\n"
        f"<b>Banned:</b> {'Yes' if target.is_banned else 'No'}\n"
        f"<b>Language:</b> {target.language_code}\n"
        f"<b>Joined:</b> {target.created_at.strftime('%Y-%m-%d %H:%M')}"
    )


async def get_user_page(
    session: AsyncSession, page: int
) -> tuple[list[User], bool]:
    repo = UserRepository(session)
    users = await repo.search(offset=page * USERS_PER_PAGE, limit=USERS_PER_PAGE + 1)
    has_more = len(users) > USERS_PER_PAGE
    return users[:USERS_PER_PAGE], has_more


async def search_users(session: AsyncSession, query: str) -> list[User]:
    repo = UserRepository(session)
    return await repo.search(query=query, limit=USERS_PER_PAGE)


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    repo = UserRepository(session)
    return await repo.get_by_id(user_id)


async def toggle_user_ban(session: AsyncSession, user_id: int) -> User | None:
    repo = UserRepository(session)
    target = await repo.get_by_id(user_id)
    if target:
        await repo.update(target, is_banned=not target.is_banned)
        await session.commit()
    return target


async def adjust_balance(
    session: AsyncSession, target_user_id: int, amount: Decimal, admin_id: int
) -> User | None:
    repo = UserRepository(session)
    target = await repo.get_by_id(target_user_id)
    if not target:
        return None

    target.balance += amount
    tx = BalanceTransaction(
        user_id=target.id,
        amount=amount,
        transaction_type="admin_adjust",
        description=f"Adjusted by admin #{admin_id}",
    )
    session.add(tx)
    await session.commit()
    return target


async def get_setting_value(session: AsyncSession, key: str) -> object:
    repo = AppSettingRepository(session)
    return await repo.get_value(key, default="(not set)")


async def toggle_setting(
    session: AsyncSession, key: str, user_id: int
) -> bool:
    repo = AppSettingRepository(session)
    current = await repo.get_value(key, default=False)
    new_val = not bool(current)
    await repo.set_value(key, new_val, updated_by_id=user_id)
    await session.commit()
    return new_val


async def update_setting(
    session: AsyncSession, key: str, raw_value: str, user_id: int
) -> None:
    parsed_value: str | int | float
    if raw_value.isdigit():
        parsed_value = int(raw_value)
    else:
        try:
            parsed_value = float(raw_value)
        except ValueError:
            parsed_value = raw_value

    repo = AppSettingRepository(session)
    await repo.set_value(key, parsed_value, updated_by_id=user_id)
    await session.commit()
