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


def find_setting_meta(key: str) -> tuple[str, str, str, list | None] | None:
    for item in MANAGED_SETTINGS:
        k, label, stype = item[0], item[1], item[2]
        choices = item[3] if len(item) > 3 else None
        if k == key:
            return k, label, stype, choices
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


def _format_profile_section(user: User) -> str:
    lines = [
        f"first_name: {user.first_name or ''}",
        f"last_name: {user.last_name or ''}",
        f"username: {user.username or ''}",
    ]
    return "[ПРОФИЛЬ / PROFILE]\n" + "\n".join(lines)


def _format_autoparse_section(ap_settings: dict) -> str:
    lines = [
        f"user_name: {ap_settings.get('user_name') or ''}",
        f"about_me: {ap_settings.get('about_me') or ''}",
        f"work_experience: {ap_settings.get('work_experience') or ''}",
        f"tech_stack: {', '.join(ap_settings.get('tech_stack') or [])}",
    ]
    return "[НАСТРОЙКИ АВТОПАРСИНГА / AUTOPARSE SETTINGS]\n" + "\n".join(lines)


def _format_work_experience_section(experiences: list) -> str:
    if not experiences:
        return "[ОПЫТ РАБОТЫ / WORK EXPERIENCE]\n(нет данных)"
    sections = []
    for i, exp in enumerate(experiences, 1):
        lines = [
            f"{i}. {exp.company_name}",
            f"   title: {exp.title or ''}",
            f"   period: {exp.period or ''}",
            f"   stack: {exp.stack or ''}",
            f"   achievements: {exp.achievements or ''}",
            f"   duties: {exp.duties or ''}",
        ]
        sections.append("\n".join(lines))
    return "[ОПЫТ РАБОТЫ / WORK EXPERIENCE]\n" + "\n\n".join(sections)


def _format_vacancy_summary_section(summaries: list) -> str:
    if not summaries:
        return "[О СЕБЕ / VACANCY SUMMARY]\n(нет данных)"
    s = summaries[0]
    lines = [
        f"excluded_industries: {s.excluded_industries or ''}",
        f"location: {s.location or ''}",
        f"remote_preference: {s.remote_preference or ''}",
        f"additional_notes: {s.additional_notes or ''}",
        "",
        f"generated_text:\n{s.generated_text or ''}",
    ]
    return "[О СЕБЕ / VACANCY SUMMARY]\n" + "\n".join(lines)


async def build_vacancy_prep_query(session: AsyncSession, user: User) -> str:
    """Build a structured text query with all user data for vacancy preparation prompts."""
    from src.bot.modules.autoparse import services as ap_service
    from src.repositories.vacancy_summary import VacancySummaryRepository
    from src.repositories.work_experience import WorkExperienceRepository

    ap_settings = await ap_service.get_user_autoparse_settings(session, user.id)
    we_repo = WorkExperienceRepository(session)
    experiences = await we_repo.get_active_by_user(user.id)
    vs_repo = VacancySummaryRepository(session)
    summaries, _ = await vs_repo.get_by_user_paginated(user.id, page=0)

    parts = [
        _format_profile_section(user),
        "\n" + _format_autoparse_section(ap_settings),
        "\n" + _format_work_experience_section(experiences),
        "\n" + _format_vacancy_summary_section(summaries),
    ]
    return "\n".join(parts)


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
