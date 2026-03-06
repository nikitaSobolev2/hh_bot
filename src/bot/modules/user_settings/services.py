from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.blacklist import VacancyBlacklist
from src.repositories.blacklist import BlacklistRepository
from src.repositories.user import UserRepository


async def set_language(session: AsyncSession, user_id: int, lang: str) -> None:
    repo = UserRepository(session)
    db_user = await repo.get_by_id(user_id)
    if db_user:
        await repo.update(db_user, language_code=lang)
        await session.commit()


async def get_blacklist_contexts(
    session: AsyncSession, user_id: int
) -> list[tuple[str, int]]:
    now = datetime.now(UTC).replace(tzinfo=None)
    stmt = (
        select(
            VacancyBlacklist.vacancy_title_context,
            func.count(VacancyBlacklist.id).label("cnt"),
        )
        .where(
            VacancyBlacklist.user_id == user_id,
            VacancyBlacklist.blacklisted_until > now,
        )
        .group_by(VacancyBlacklist.vacancy_title_context)
    )
    result = await session.execute(stmt)
    return [(row[0], row[1]) for row in result.all()]


def format_blacklist_text(contexts: list[tuple[str, int]]) -> str:
    lines = ["<b>🗑 Blacklist Management</b>\n"]
    for ctx_name, count in contexts:
        lines.append(f"• <b>{ctx_name}</b> — {count} vacancies")
    return "\n".join(lines)


async def clear_all_blacklist(session: AsyncSession, user_id: int) -> int:
    repo = BlacklistRepository(session)
    count = await repo.clear_for_user(user_id)
    await session.commit()
    return count


async def clear_blacklist_by_context(
    session: AsyncSession, user_id: int, context: str
) -> int:
    repo = BlacklistRepository(session)
    count = await repo.clear_by_context(user_id, context)
    await session.commit()
    return count
