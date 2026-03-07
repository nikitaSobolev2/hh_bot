from aiogram.types import BufferedInputFile
from src.core.i18n import I18nContext
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.parsing import AggregatedResult, ParsingCompany
from src.repositories.blacklist import BlacklistRepository
from src.repositories.parsing import (
    AggregatedResultRepository,
    ParsingCompanyRepository,
)
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
) -> int:
    repo = ParsingCompanyRepository(session)
    company = await repo.create(
        user_id=user_id,
        vacancy_title=vacancy_title,
        search_url=search_url,
        keyword_filter=keyword_filter,
        target_count=target_count,
        status="pending",
    )
    await session.commit()
    return company.id


def dispatch_parsing_task(company_id: int, user_id: int, include_blacklisted: bool) -> None:
    from src.worker.tasks.parsing import run_parsing_company

    run_parsing_company.delay(company_id, user_id, include_blacklisted)


async def clone_and_dispatch(session: AsyncSession, source_company_id: int, user_id: int) -> int:
    repo = ParsingCompanyRepository(session)
    source = await repo.get_by_id(source_company_id)
    if not source:
        raise ValueError(f"ParsingCompany {source_company_id} not found")

    new_id = await create_parsing_company(
        session=session,
        user_id=user_id,
        vacancy_title=source.vacancy_title,
        search_url=source.search_url,
        keyword_filter=source.keyword_filter or "",
        target_count=source.target_count,
    )
    dispatch_parsing_task(new_id, user_id, include_blacklisted=False)
    return new_id


async def get_company_with_details(session: AsyncSession, company_id: int) -> ParsingCompany | None:
    repo = ParsingCompanyRepository(session)
    return await repo.get_with_details(company_id)


async def get_company_by_id(session: AsyncSession, company_id: int) -> ParsingCompany | None:
    repo = ParsingCompanyRepository(session)
    return await repo.get_by_id(company_id)


def format_company_detail(
    company: ParsingCompany, i18n: I18nContext
) -> str:
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
    return i18n.get(
        "parsing-confirm",
        title=data["vacancy_title"],
        count=str(data["target_count"]),
        filter=filter_val,
        blacklist=bl_text,
    )


def dispatch_key_phrases_task(
    company_id: int,
    user_id: int,
    style_key: str,
    count: int,
    lang: str,
    chat_id: int,
) -> None:
    from src.worker.tasks.ai import generate_key_phrases_task

    generate_key_phrases_task.delay(
        company_id, user_id, style_key, count, chat_id, lang,
    )
