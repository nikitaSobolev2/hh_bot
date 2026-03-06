from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import User
from src.repositories.blacklist import BlacklistRepository
from src.repositories.parsing import ParsingCompanyRepository


def format_profile(user: User) -> str:
    return (
        f"<b>👤 Profile</b>\n\n"
        f"<b>Name:</b> {user.first_name} {user.last_name or ''}\n"
        f"<b>Username:</b> @{user.username or '—'}\n"
        f"<b>Role:</b> {user.role.name}\n"
        f"<b>Balance:</b> {user.balance}\n"
        f"<b>Language:</b> {user.language_code}\n"
        f"<b>Joined:</b> {user.created_at.strftime('%Y-%m-%d')}"
    )


async def get_stats(session: AsyncSession, user_id: int) -> str:
    parsing_repo = ParsingCompanyRepository(session)
    blacklist_repo = BlacklistRepository(session)
    total_parsings = await parsing_repo.count_by_user(user_id)
    blacklisted = await blacklist_repo.count_active(user_id)
    return (
        f"<b>📊 Stats</b>\n\n"
        f"Total parsings: {total_parsings}\n"
        f"Active blacklisted vacancies: {blacklisted}"
    )


def format_referral_link(user: User) -> str:
    link = f"https://t.me/hh_parser_bot?start=ref_{user.referral_code}"
    return (
        f"<b>🔗 Referral Link</b>\n\n"
        f"Share this link to invite friends:\n"
        f"<code>{link}</code>\n\n"
        f"Your referral code: <code>{user.referral_code}</code>"
    )
