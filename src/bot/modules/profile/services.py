from sqlalchemy.ext.asyncio import AsyncSession

from src.core.i18n import I18nContext
from src.models.user import User
from src.repositories.blacklist import BlacklistRepository
from src.repositories.parsing import ParsingCompanyRepository


def format_profile(user: User, i18n: I18nContext) -> str:
    lines = [
        i18n.get("profile-title"),
        "",
        i18n.get("profile-name", first_name=user.first_name, last_name=user.last_name or ""),
        i18n.get("profile-username", username=user.username or "—"),
        i18n.get("profile-role", role=user.role.name),
        i18n.get("profile-balance", balance=str(user.balance)),
        i18n.get("profile-language", language=user.language_code),
        i18n.get("profile-joined", date=user.created_at.strftime("%Y-%m-%d")),
    ]
    return "\n".join(lines)


async def get_stats(session: AsyncSession, user_id: int, i18n: I18nContext) -> str:
    parsing_repo = ParsingCompanyRepository(session)
    blacklist_repo = BlacklistRepository(session)
    total_parsings = await parsing_repo.count_by_user(user_id)
    blacklisted = await blacklist_repo.count_active(user_id)
    lines = [
        i18n.get("stats-title"),
        "",
        i18n.get("stats-total-parsings", count=str(total_parsings)),
        i18n.get("stats-blacklisted", count=str(blacklisted)),
    ]
    return "\n".join(lines)


def format_referral_link(user: User, i18n: I18nContext) -> str:
    link = f"https://t.me/hh_parser_bot?start=ref_{user.referral_code}"
    lines = [
        i18n.get("referral-title"),
        "",
        i18n.get("referral-share"),
        f"<code>{link}</code>",
        "",
        i18n.get("referral-code", code=user.referral_code),
    ]
    return "\n".join(lines)
