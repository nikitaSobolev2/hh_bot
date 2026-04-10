"""Business logic for the autoparse bot module."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.autoparse import AutoparseCompany, AutoparsedVacancy
from src.repositories.autoparse import AutoparseCompanyRepository, AutoparsedVacancyRepository
from src.repositories.user import UserRepository
from src.repositories.vacancy_feed import VacancyFeedSessionRepository
from src.services.autoparse_delivery import revoke_scheduled_delivery_async
from src.services.autoparse_profile import derive_tech_stack_from_experiences
from src.services.autoparse_use_cases import format_company_detail

__all__ = (
    "COVER_LETTER_STYLES",
    "DEFAULT_COVER_LETTER_STYLE",
    "create_autoparse_company",
    "derive_tech_stack_from_experiences",
    "format_company_detail",
    "generate_full_md",
    "generate_links_txt",
    "generate_summary_txt",
    "get_all_vacancies",
    "get_autoparse_detail",
    "get_reacted_vacancy_ids_for_user",
    "get_user_autoparse_companies",
    "get_user_autoparse_settings",
    "get_vacancy_count",
    "mark_parsing_started",
    "reset_company_vacancy_pool",
    "soft_delete_autoparse_company",
    "toggle_autoparse_keyword_check",
    "toggle_autoparse_company",
    "update_user_autoparse_settings",
)

async def create_autoparse_company(
    session: AsyncSession,
    user_id: int,
    title: str,
    url: str,
    keywords: str,
    skills: str,
    *,
    include_reacted_in_feed: bool = False,
    keyword_check_enabled: bool = True,
    parse_mode: str = "api",
    parse_hh_linked_account_id: int | None = None,
) -> AutoparseCompany:
    repo = AutoparseCompanyRepository(session)
    company = await repo.create(
        user_id=user_id,
        vacancy_title=title,
        search_url=url,
        keyword_filter=keywords,
        keyword_check_enabled=keyword_check_enabled,
        skills=skills,
        include_reacted_in_feed=include_reacted_in_feed,
        parse_mode=parse_mode,
        parse_hh_linked_account_id=parse_hh_linked_account_id,
    )
    await session.commit()
    return company


async def get_user_autoparse_companies(
    session: AsyncSession,
    user_id: int,
    page: int = 0,
    per_page: int = 5,
) -> tuple[list[AutoparseCompany], int]:
    repo = AutoparseCompanyRepository(session)
    total = await repo.count_by_user(user_id)
    companies = await repo.get_by_user(user_id, offset=page * per_page, limit=per_page)
    return companies, total


async def toggle_autoparse_company(
    session: AsyncSession,
    company_id: int,
    user_id: int | None = None,
) -> AutoparseCompany | None:
    repo = AutoparseCompanyRepository(session)
    company = (
        await repo.get_by_id_for_user(company_id, user_id)
        if user_id is not None
        else await repo.get_by_id(company_id)
    )
    if not company:
        return None
    await repo.toggle(company)
    await session.commit()
    return company


async def toggle_autoparse_keyword_check(
    session: AsyncSession,
    company_id: int,
    user_id: int | None = None,
) -> AutoparseCompany | None:
    repo = AutoparseCompanyRepository(session)
    company = (
        await repo.get_by_id_for_user(company_id, user_id)
        if user_id is not None
        else await repo.get_by_id(company_id)
    )
    if not company:
        return None
    await repo.update(company, keyword_check_enabled=not company.keyword_check_enabled)
    await session.commit()
    return company


async def soft_delete_autoparse_company(
    session: AsyncSession,
    company_id: int,
    user_id: int | None = None,
) -> bool:
    repo = AutoparseCompanyRepository(session)
    company = (
        await repo.get_by_id_for_user(company_id, user_id)
        if user_id is not None
        else await repo.get_by_id(company_id)
    )
    if not company:
        return False
    await repo.soft_delete(company_id, user_id)
    await session.commit()

    if user_id is not None:
        await _revoke_scheduled_delivery_async(company_id, user_id)
    return True


async def _revoke_scheduled_delivery_async(company_id: int, user_id: int) -> None:
    await revoke_scheduled_delivery_async(company_id, user_id)


async def get_reacted_vacancy_ids_for_user(session: AsyncSession, user_id: int) -> set[int]:
    """Return vacancy IDs the user has liked or disliked across all autoparse companies."""
    feed_repo = VacancyFeedSessionRepository(session)
    liked = await feed_repo.get_all_liked_vacancy_ids_for_user(user_id)
    disliked = await feed_repo.get_all_disliked_vacancy_ids_for_user(user_id)
    return liked | disliked


async def get_autoparse_detail(
    session: AsyncSession,
    company_id: int,
    user_id: int | None = None,
) -> AutoparseCompany | None:
    repo = AutoparseCompanyRepository(session)
    if user_id is None:
        return await repo.get_by_id(company_id)
    return await repo.get_by_id_for_user(company_id, user_id)


async def mark_parsing_started(
    session: AsyncSession,
    company_id: int,
    user_id: int | None = None,
) -> AutoparseCompany | None:
    repo = AutoparseCompanyRepository(session)
    company = (
        await repo.get_by_id_for_user(company_id, user_id)
        if user_id is not None
        else await repo.get_by_id(company_id)
    )
    if company:
        await repo.update(company, last_parsed_at=datetime.now(UTC).replace(tzinfo=None))
        await session.commit()
    return company


async def reset_company_vacancy_pool(
    session: AsyncSession,
    company_id: int,
    user_id: int | None = None,
) -> AutoparseCompany | None:
    company_repo = AutoparseCompanyRepository(session)
    company = (
        await company_repo.get_by_id_for_user(company_id, user_id)
        if user_id is not None
        else await company_repo.get_by_id(company_id)
    )
    if not company:
        return None

    feed_repo = VacancyFeedSessionRepository(session)
    vacancy_repo = AutoparsedVacancyRepository(session)
    await feed_repo.delete_all_for_company(company_id)
    await vacancy_repo.delete_all_by_company(company_id)
    await company_repo.update(company, last_delivered_at=None)
    await session.commit()
    return company


async def get_vacancy_count(session: AsyncSession, company_id: int) -> int:
    repo = AutoparsedVacancyRepository(session)
    return await repo.count_by_company(company_id)


async def get_all_vacancies(
    session: AsyncSession,
    company_id: int,
    user_id: int | None = None,
) -> list[AutoparsedVacancy]:
    if user_id is not None:
        company_repo = AutoparseCompanyRepository(session)
        company = await company_repo.get_by_id_for_user(company_id, user_id)
        if company is None:
            return []
    repo = AutoparsedVacancyRepository(session)
    return await repo.get_all_by_company(company_id)


def generate_links_txt(vacancies: list[AutoparsedVacancy]) -> str:
    return "\n".join(v.url for v in vacancies)


def generate_summary_txt(vacancies: list[AutoparsedVacancy]) -> str:
    lines = ["Title | Company | Salary | Compatibility | Link"]
    for v in vacancies:
        compat = f"{v.compatibility_score:.0f}%" if v.compatibility_score is not None else "N/A"
        lines.append(
            f"{v.title} | {v.company_name or '—'} | {v.salary or '—'} | {compat} | {v.url}"
        )
    return "\n".join(lines)


def generate_full_md(vacancies: list[AutoparsedVacancy]) -> str:
    parts: list[str] = []
    for v in vacancies:
        compat = f"{v.compatibility_score:.0f}%" if v.compatibility_score is not None else "N/A"
        company_line = (
            f"[{v.company_name}]({v.company_url})"
            if v.company_name and v.company_url
            else (v.company_name or "—")
        )
        tags_line = ", ".join(v.tags) if v.tags else "—"
        section = (
            f"# {v.title}\n"
            f"- **Company**: {company_line}\n"
            f"- **Salary**: {v.salary or '—'}\n"
            f"- **Experience**: {v.work_experience or '—'}\n"
            f"- **Work Format**: {v.work_formats or '—'}\n"
            f"- **Employment**: {v.employment_type or '—'}\n"
            f"- **Schedule**: {v.work_schedule or '—'}\n"
            f"- **Tags**: {tags_line}\n"
            f"- **Compatibility**: {compat}\n"
            f"- **Link**: {v.url}\n"
            f"## Description\n"
            f"{v.description[:2000] if v.description else '—'}\n"
            f"---"
        )
        parts.append(section)
    return "\n\n".join(parts)


DEFAULT_COVER_LETTER_STYLE = "professional"
COVER_LETTER_STYLES = ("professional", "friendly", "concise", "detailed")


async def get_user_autoparse_settings(session: AsyncSession, user_id: int) -> dict:
    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(user_id)
    if not user or not user.autoparse_settings:
        return {
            "send_time": "12:00",
            "work_experience": "",
            "tech_stack": [],
            "cover_letter_style": DEFAULT_COVER_LETTER_STYLE,
            "user_name": "",
            "about_me": "",
        }
    defaults = {
        "send_time": "12:00",
        "work_experience": "",
        "tech_stack": [],
        "cover_letter_style": DEFAULT_COVER_LETTER_STYLE,
        "user_name": "",
        "about_me": "",
    }
    defaults.update(user.autoparse_settings)
    return defaults


async def update_user_autoparse_settings(
    session: AsyncSession, user_id: int, **kwargs: object
) -> None:
    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(user_id)
    if not user:
        return
    current = dict(user.autoparse_settings) if user.autoparse_settings else {}
    current.update(kwargs)
    await user_repo.update(user, autoparse_settings=current)
    await session.commit()


