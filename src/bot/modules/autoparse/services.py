"""Business logic for the autoparse bot module."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.autoparse import AutoparseCompany, AutoparsedVacancy
from src.models.work_experience import UserWorkExperience
from src.repositories.autoparse import AutoparseCompanyRepository, AutoparsedVacancyRepository
from src.repositories.user import UserRepository
from src.repositories.vacancy_feed import VacancyFeedSessionRepository

if TYPE_CHECKING:
    from src.core.i18n import I18nContext


async def create_autoparse_company(
    session: AsyncSession,
    user_id: int,
    title: str,
    url: str,
    keywords: str,
    skills: str,
    *,
    include_reacted_in_feed: bool = False,
) -> AutoparseCompany:
    repo = AutoparseCompanyRepository(session)
    company = await repo.create(
        user_id=user_id,
        vacancy_title=title,
        search_url=url,
        keyword_filter=keywords,
        skills=skills,
        include_reacted_in_feed=include_reacted_in_feed,
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


async def toggle_autoparse_company(session: AsyncSession, company_id: int) -> bool:
    repo = AutoparseCompanyRepository(session)
    company = await repo.get_by_id(company_id)
    if not company:
        return False
    new_state = await repo.toggle(company)
    await session.commit()
    return new_state


async def soft_delete_autoparse_company(
    session: AsyncSession,
    company_id: int,
    user_id: int | None = None,
) -> None:
    repo = AutoparseCompanyRepository(session)
    await repo.soft_delete(company_id)
    await session.commit()

    if user_id is not None:
        await _revoke_scheduled_delivery_async(company_id, user_id)


async def _revoke_scheduled_delivery_async(company_id: int, user_id: int) -> None:
    from src.core.celery_async import run_sync_in_thread
    from src.core.redis import create_async_redis
    from src.worker.app import celery_app
    from src.worker.tasks.autoparse import _DELIVER_TASK_PREFIX

    task_key = f"{_DELIVER_TASK_PREFIX}{company_id}:{user_id}"
    redis = create_async_redis()
    try:
        scheduled_id = await redis.get(task_key)
        if scheduled_id:
            await run_sync_in_thread(
                celery_app.control.revoke,
                scheduled_id,
                terminate=False,
            )
            await redis.delete(task_key)
    finally:
        await redis.aclose()


async def get_reacted_vacancy_ids_for_user(session: AsyncSession, user_id: int) -> set[int]:
    """Return vacancy IDs the user has liked or disliked across all autoparse companies."""
    feed_repo = VacancyFeedSessionRepository(session)
    liked = await feed_repo.get_all_liked_vacancy_ids_for_user(user_id)
    disliked = await feed_repo.get_all_disliked_vacancy_ids_for_user(user_id)
    return liked | disliked


async def get_autoparse_detail(session: AsyncSession, company_id: int) -> AutoparseCompany | None:
    repo = AutoparseCompanyRepository(session)
    return await repo.get_by_id(company_id)


async def mark_parsing_started(session: AsyncSession, company_id: int) -> AutoparseCompany | None:
    repo = AutoparseCompanyRepository(session)
    company = await repo.get_by_id(company_id)
    if company:
        await repo.update(company, last_parsed_at=datetime.now(UTC).replace(tzinfo=None))
        await session.commit()
    return company


async def get_vacancy_count(session: AsyncSession, company_id: int) -> int:
    repo = AutoparsedVacancyRepository(session)
    return await repo.count_by_company(company_id)


async def get_all_vacancies(session: AsyncSession, company_id: int) -> list[AutoparsedVacancy]:
    repo = AutoparsedVacancyRepository(session)
    return await repo.get_all_by_company(company_id)


def format_company_detail(
    company: AutoparseCompany,
    vacancies_count: int,
    i18n: I18nContext,
) -> str:
    status = (
        i18n.get("autoparse-status-enabled")
        if company.is_enabled
        else i18n.get("autoparse-status-disabled")
    )
    last_run = company.last_parsed_at.strftime("%Y-%m-%d %H:%M") if company.last_parsed_at else "—"
    url_label = i18n.get("autoparse-detail-url")
    lines = [
        f"<b>{i18n.get('autoparse-detail-title')}</b>",
        "",
        f"<b>{company.vacancy_title}</b>",
        f"{i18n.get('autoparse-detail-status')}: {status}",
        f"{url_label}: <a href='{company.search_url}'>{url_label}</a>",
        f"{i18n.get('autoparse-detail-keywords')}: {company.keyword_filter or '—'}",
        f"{i18n.get('autoparse-detail-skills')}: {company.skills or '—'}",
        "",
        f"{i18n.get('autoparse-detail-metrics')}:",
        f"  {i18n.get('autoparse-detail-runs')}: {company.total_runs}",
        f"  {i18n.get('autoparse-detail-vacancies')}: {vacancies_count}",
        f"  {i18n.get('autoparse-detail-last-run')}: {last_run}",
    ]
    return "\n".join(lines)


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


def derive_tech_stack_from_experiences(experiences: list[UserWorkExperience]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for exp in experiences:
        for tech in exp.stack.split(","):
            normalized = tech.strip()
            if normalized and normalized.lower() not in seen:
                seen.add(normalized.lower())
                result.append(normalized)
    return result
