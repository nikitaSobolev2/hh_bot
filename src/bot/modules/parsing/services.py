from aiogram import Bot
from aiogram.types import BufferedInputFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.modules.parsing.keyboards import KEY_PHRASES_STYLES
from src.models.parsing import AggregatedResult, ParsingCompany
from src.repositories.blacklist import BlacklistRepository
from src.repositories.parsing import (
    AggregatedResultRepository,
    ParsingCompanyRepository,
)
from src.services.ai.client import AIClient
from src.services.ai.streaming import stream_to_telegram
from src.services.parser.report import ReportGenerator


async def get_user_companies(
    session: AsyncSession, user_id: int, limit: int = 10
) -> list[ParsingCompany]:
    repo = ParsingCompanyRepository(session)
    return await repo.get_by_user(user_id, limit=limit)


async def get_blacklisted_count(
    session: AsyncSession, user_id: int, vacancy_title: str
) -> int:
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


async def get_company_with_details(
    session: AsyncSession, company_id: int
) -> ParsingCompany | None:
    repo = ParsingCompanyRepository(session)
    return await repo.get_with_details(company_id)


async def get_company_by_id(
    session: AsyncSession, company_id: int
) -> ParsingCompany | None:
    repo = ParsingCompanyRepository(session)
    return await repo.get_by_id(company_id)


def format_company_detail(company: ParsingCompany) -> str:
    text = (
        f"<b>{company.vacancy_title}</b>\n\n"
        f"<b>Status:</b> {company.status}\n"
        f"<b>Processed:</b> {company.vacancies_processed}/{company.target_count}\n"
        f"<b>Filter:</b> {company.keyword_filter or 'none'}\n"
        f"<b>Created:</b> {company.created_at.strftime('%Y-%m-%d %H:%M')}\n"
    )
    if company.completed_at:
        text += f"<b>Completed:</b> {company.completed_at.strftime('%Y-%m-%d %H:%M')}\n"
    return text


async def get_aggregated_result(
    session: AsyncSession, company_id: int
) -> AggregatedResult | None:
    repo = AggregatedResultRepository(session)
    return await repo.get_by_company(company_id)


def build_report(company: ParsingCompany, agg: AggregatedResult) -> ReportGenerator:
    return ReportGenerator(
        vacancy_title=company.vacancy_title,
        top_keywords=agg.top_keywords or {},
        top_skills=agg.top_skills or {},
        vacancies_processed=company.vacancies_processed,
        key_phrases=agg.key_phrases,
        key_phrases_style=agg.key_phrases_style,
    )


def generate_document(content: str, filename: str) -> BufferedInputFile:
    return BufferedInputFile(content.encode("utf-8"), filename=filename)


def format_confirmation(data: dict, include_blacklisted: bool) -> str:
    return (
        f"<b>🚀 Parsing Started!</b>\n\n"
        f"<b>Title:</b> {data['vacancy_title']}\n"
        f"<b>Target:</b> {data['target_count']} vacancies\n"
        f"<b>Filter:</b> {data.get('keyword_filter') or 'none'}\n"
        f"<b>Blacklist:</b> "
        f"{'including all' if include_blacklisted else 'skipping blacklisted'}\n\n"
        f"You will be notified when results are ready."
    )


async def generate_key_phrases_stream(
    bot: Bot,
    session: AsyncSession,
    company: ParsingCompany,
    agg: AggregatedResult,
    style_key: str,
    count: int,
    chat_id: int,
) -> None:
    style_label = KEY_PHRASES_STYLES.get(style_key, style_key)
    sorted_kw = sorted(agg.top_keywords.items(), key=lambda x: -x[1])
    top_keywords = [kw for kw, _ in sorted_kw[:count]]

    ai = AIClient()
    result = await stream_to_telegram(
        bot=bot,
        chat_id=chat_id,
        ai_client=ai,
        resume_title=company.vacancy_title,
        keywords=top_keywords,
        style=style_label,
        initial_text=(
            f"<b>✨ Key Phrases for {company.vacancy_title}</b>\n"
            f"Style: {style_label}\n\n"
        ),
    )

    if result:
        agg_repo = AggregatedResultRepository(session)
        agg_obj = await agg_repo.get_by_company(company.id)
        if agg_obj:
            agg_obj.key_phrases = result
            agg_obj.key_phrases_style = style_label
            await session.commit()
