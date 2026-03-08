from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.modules.admin.keyboards import MANAGED_SETTINGS
from src.config import sync_setting_to_runtime
from src.core.i18n import I18nContext, get_text
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


def format_user_detail(target: User, i18n: I18nContext) -> str:
    banned_text = i18n.get("yes") if target.is_banned else i18n.get("no")
    lines = [
        i18n.get("admin-user-detail-title", id=str(target.id)),
        "",
        i18n.get("admin-user-detail-name", name=f"{target.first_name} {target.last_name or ''}"),
        i18n.get("admin-user-detail-username", username=target.username or "—"),
        i18n.get("admin-user-detail-telegram-id", telegram_id=str(target.telegram_id)),
        i18n.get("admin-user-detail-role", role=target.role.name),
        i18n.get("admin-user-detail-balance", balance=str(target.balance)),
        i18n.get("admin-user-detail-banned", banned=banned_text),
        i18n.get("admin-user-detail-language", language=target.language_code),
        i18n.get("admin-user-detail-joined", date=target.created_at.strftime("%Y-%m-%d %H:%M")),
    ]
    return "\n".join(lines)


async def get_user_page(session: AsyncSession, page: int) -> tuple[list[User], bool]:
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
    session: AsyncSession,
    target_user_id: int,
    amount: Decimal,
    admin_id: int,
    locale: str = "ru",
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
        description=get_text("admin-balance-description", locale, admin_id=str(admin_id)),
    )
    session.add(tx)
    await session.commit()
    return target


async def get_setting_value(session: AsyncSession, key: str, locale: str = "ru") -> object:
    repo = AppSettingRepository(session)
    return await repo.get_value(key, default=get_text("admin-not-set", locale))


async def toggle_setting(session: AsyncSession, key: str, user_id: int) -> bool:
    repo = AppSettingRepository(session)
    current = await repo.get_value(key, default=False)
    new_val = not bool(current)
    await repo.set_value(key, new_val, updated_by_id=user_id)
    await session.commit()
    sync_setting_to_runtime(key, new_val)
    return new_val


async def update_setting(session: AsyncSession, key: str, raw_value: str, user_id: int) -> None:
    parsed_value: str | int | float
    try:
        parsed_value = int(raw_value)
    except ValueError:
        try:
            parsed_value = float(raw_value)
        except ValueError:
            parsed_value = raw_value

    repo = AppSettingRepository(session)
    await repo.set_value(key, parsed_value, updated_by_id=user_id)
    await session.commit()
    sync_setting_to_runtime(key, parsed_value)
