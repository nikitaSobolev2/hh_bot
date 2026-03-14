from aiogram.types import BufferedInputFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.i18n import I18nContext
from src.models.parsing import AggregatedResult, ParsingCompany
from src.models.work_experience import UserWorkExperience
from src.repositories.blacklist import BlacklistRepository
from src.repositories.parsing import (
    AggregatedResultRepository,
    ParsingCompanyRepository,
)
from src.repositories.work_experience import WorkExperienceRepository
from src.services.parser.report import ReportGenerator


async def get_user_companies(
    session: AsyncSession, user_id: int, limit: int = 10
) -> list[ParsingCompany]:
    repo = ParsingCompanyRepository(session)
    return await repo.get_by_user(user_id, limit=limit)


async def get_blacklisted_count(session: AsyncSession, user_id: int, vacancy_title: str) -> int:
    repo = BlacklistRepository(session)
    ids = await repo.get_active_ids(user_id, vacancy_title)
    return len(ids)


async def create_parsing_company(
    session: AsyncSession,
    user_id: int,
    vacancy_title: str,
    search_url: str,
    keyword_filter: str,
    target_count: int,
    use_compatibility_check: bool = False,
    compatibility_threshold: int | None = None,
) -> int:
    repo = ParsingCompanyRepository(session)
    company = await repo.create(
        user_id=user_id,
        vacancy_title=vacancy_title,
        search_url=search_url,
        keyword_filter=keyword_filter,
        target_count=target_count,
        status="pending",
        use_compatibility_check=use_compatibility_check,
        compatibility_threshold=compatibility_threshold,
    )
    await session.commit()
    return company.id


async def dispatch_parsing_task(
    company_id: int,
    user_id: int,
    include_blacklisted: bool,
    telegram_chat_id: int = 0,
) -> None:
    from src.core.celery_async import run_celery_task
    from src.worker.tasks.parsing import run_parsing_company

    await run_celery_task(
        run_parsing_company,
        company_id,
        user_id,
        include_blacklisted,
        telegram_chat_id,
    )


async def clone_and_dispatch(
    session: AsyncSession,
    source_company_id: int,
    user_id: int,
    telegram_chat_id: int = 0,
    target_count: int | None = None,
    use_compatibility_check: bool | None = None,
    compatibility_threshold: int | None = None,
) -> int:
    repo = ParsingCompanyRepository(session)
    source = await repo.get_by_id(source_company_id)
    if not source:
        raise ValueError(f"ParsingCompany {source_company_id} not found")

    final_use_compat = (
        use_compatibility_check
        if use_compatibility_check is not None
        else source.use_compatibility_check
    )
    final_threshold = (
        compatibility_threshold
        if use_compatibility_check is not None
        else source.compatibility_threshold
    )

    new_id = await create_parsing_company(
        session=session,
        user_id=user_id,
        vacancy_title=source.vacancy_title,
        search_url=source.search_url,
        keyword_filter=source.keyword_filter or "",
        target_count=target_count if target_count is not None else source.target_count,
        use_compatibility_check=final_use_compat,
        compatibility_threshold=final_threshold,
    )
    await dispatch_parsing_task(
        new_id,
        user_id,
        include_blacklisted=False,
        telegram_chat_id=telegram_chat_id,
    )
    return new_id


async def get_company_with_details(session: AsyncSession, company_id: int) -> ParsingCompany | None:
    repo = ParsingCompanyRepository(session)
    return await repo.get_with_details(company_id)


async def get_company_by_id(session: AsyncSession, company_id: int) -> ParsingCompany | None:
    repo = ParsingCompanyRepository(session)
    return await repo.get_by_id(company_id)


async def get_company_for_user(
    session: AsyncSession, company_id: int, user_id: int
) -> ParsingCompany | None:
    """Return company if it belongs to user and is not soft-deleted."""
    repo = ParsingCompanyRepository(session)
    return await repo.get_by_id_for_user(company_id, user_id)


async def soft_delete_parsing(session: AsyncSession, company_id: int, user_id: int) -> bool:
    """Soft-delete a parsing. Returns True if deleted, False if not found or not owned."""
    repo = ParsingCompanyRepository(session)
    company = await repo.get_by_id_for_user(company_id, user_id)
    if not company:
        return False
    await repo.soft_delete(company_id)
    await session.commit()
    return True


def format_company_detail(company: ParsingCompany, i18n: I18nContext) -> str:
    filter_val = company.keyword_filter or i18n.get("detail-filter-none")
    processed = str(company.vacancies_processed)
    total = str(company.target_count)
    created = company.created_at.strftime("%Y-%m-%d %H:%M")
    text = (
        f"<b>{company.vacancy_title}</b>\n\n"
        f"{i18n.get('detail-status', status=company.status)}\n"
        f"{i18n.get('detail-processed', processed=processed, total=total)}\n"
        f"{i18n.get('detail-filter', filter=filter_val)}\n"
        f"{i18n.get('detail-created', date=created)}\n"
    )
    if company.completed_at:
        completed = company.completed_at.strftime("%Y-%m-%d %H:%M")
        text += f"{i18n.get('detail-completed', date=completed)}\n"
    return text


async def get_aggregated_result(session: AsyncSession, company_id: int) -> AggregatedResult | None:
    repo = AggregatedResultRepository(session)
    return await repo.get_by_company(company_id)


def build_report(
    company: ParsingCompany,
    agg: AggregatedResult,
    locale: str = "ru",
) -> ReportGenerator:
    return ReportGenerator(
        vacancy_title=company.vacancy_title,
        top_keywords=agg.top_keywords or {},
        top_skills=agg.top_skills or {},
        vacancies_processed=company.vacancies_processed,
        key_phrases=agg.key_phrases,
        key_phrases_style=agg.key_phrases_style,
        locale=locale,
    )


def generate_document(content: str, filename: str) -> BufferedInputFile:
    return BufferedInputFile(content.encode("utf-8"), filename=filename)


def format_confirmation(data: dict, include_blacklisted: bool, i18n: I18nContext) -> str:
    filter_val = data.get("keyword_filter") or i18n.get("detail-filter-none")
    bl_text = (
        i18n.get("parsing-confirm-include-all")
        if include_blacklisted
        else i18n.get("parsing-confirm-skip-bl")
    )
    base = i18n.get(
        "parsing-confirm",
        title=data["vacancy_title"],
        count=str(data["target_count"]),
        filter=filter_val,
        blacklist=bl_text,
    )
    threshold = data.get("compatibility_threshold")
    if data.get("use_compatibility_check") and threshold is not None:
        base += "\n" + i18n.get("parsing-confirm-compat", threshold=str(threshold))
    return base


async def get_active_work_experiences(
    session: AsyncSession, user_id: int
) -> list[UserWorkExperience]:
    repo = WorkExperienceRepository(session)
    return await repo.get_active_by_user(user_id)


async def count_active_work_experiences(session: AsyncSession, user_id: int) -> int:
    repo = WorkExperienceRepository(session)
    return await repo.count_active_by_user(user_id)


async def add_work_experience(
    session: AsyncSession,
    user_id: int,
    company_name: str,
    stack: str,
    *,
    title: str | None = None,
    period: str | None = None,
    achievements: str | None = None,
    duties: str | None = None,
) -> UserWorkExperience:
    repo = WorkExperienceRepository(session)
    experience = await repo.create(
        user_id=user_id,
        company_name=company_name,
        stack=stack,
        title=title,
        period=period,
        achievements=achievements,
        duties=duties,
    )
    await session.commit()
    return experience


async def deactivate_work_experience(session: AsyncSession, work_exp_id: int, user_id: int) -> bool:
    repo = WorkExperienceRepository(session)
    deactivated = await repo.deactivate(work_exp_id, user_id)
    if deactivated:
        await session.commit()
    return deactivated


async def dispatch_key_phrases_task(
    company_id: int,
    user_id: int,
    style_key: str,
    count: int,
    lang: str,
    chat_id: int,
    mode: str = "",
) -> None:
    from src.core.celery_async import run_celery_task
    from src.worker.tasks.ai import generate_key_phrases_task

    await run_celery_task(
        generate_key_phrases_task,
        company_id,
        user_id,
        style_key,
        count,
        chat_id,
        lang,
        mode,
    )
