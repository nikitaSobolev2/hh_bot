"""Service layer for the My Interviews module.

Contains pure data-access and AI-orchestration logic with no Telegram coupling.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.interview import ImprovementStatus, Interview, InterviewImprovement
from src.repositories.interview import (
    InterviewImprovementRepository,
    InterviewQuestionRepository,
    InterviewRepository,
)
from src.services.ai.client import AIClient, close_ai_client
from src.services.ai.interview_parser import parse_interview_analysis

_PAGE_SIZE = 5


async def get_interviews_paginated(
    session: AsyncSession,
    user_id: int,
    page: int,
) -> tuple[Sequence[Interview], int]:
    repo = InterviewRepository(session)
    interviews = await repo.get_by_user_paginated(user_id, page, _PAGE_SIZE)
    total = await repo.count_by_user(user_id)
    return interviews, total


async def get_interview_detail(
    session: AsyncSession,
    interview_id: int,
) -> Interview | None:
    return await InterviewRepository(session).get_with_relations(interview_id)


async def soft_delete_interview(session: AsyncSession, interview_id: int) -> None:
    await InterviewRepository(session).soft_delete(interview_id)
    await session.commit()


async def create_interview(
    session: AsyncSession,
    user_id: int,
    vacancy_title: str,
    vacancy_description: str | None,
    company_name: str | None,
    experience_level: str | None,
    hh_vacancy_url: str | None,
) -> Interview:
    interview = await InterviewRepository(session).create(
        user_id=user_id,
        vacancy_title=vacancy_title,
        vacancy_description=vacancy_description,
        company_name=company_name,
        experience_level=experience_level,
        hh_vacancy_url=hh_vacancy_url,
    )
    await session.commit()
    return interview


async def analyze_and_save(
    session: AsyncSession,
    interview_id: int,
    vacancy_title: str,
    vacancy_description: str | None,
    company_name: str | None,
    experience_level: str | None,
    questions_answers: list[dict[str, str]],
    user_improvement_notes: str | None,
) -> tuple[str, list[InterviewImprovement]]:
    """Run AI analysis, persist results, and return (summary, improvements)."""
    ai_client = AIClient()
    try:
        raw_response = await ai_client.analyze_interview(
            vacancy_title=vacancy_title,
            vacancy_description=vacancy_description,
            company_name=company_name,
            experience_level=experience_level,
            questions_answers=questions_answers,
            user_improvement_notes=user_improvement_notes,
        )
    finally:
        await close_ai_client(ai_client)

    summary, improvement_data = parse_interview_analysis(raw_response)

    interview_repo = InterviewRepository(session)
    interview = await interview_repo.get_by_id(interview_id)
    if interview:
        await interview_repo.update(interview, ai_summary=summary)

    improvement_repo = InterviewImprovementRepository(session)
    improvements: list[InterviewImprovement] = []
    for item in improvement_data:
        imp = await improvement_repo.create(
            interview_id=interview_id,
            technology_title=item["title"],
            summary=item["summary"],
            status=ImprovementStatus.PENDING,
        )
        improvements.append(imp)

    await session.commit()
    return summary, improvements


async def generate_and_save_improvement_flow(
    session: AsyncSession,
    improvement_id: int,
    vacancy_title: str,
    vacancy_description: str | None,
) -> str:
    """Generate AI improvement flow and persist it. Returns the generated text."""
    repo = InterviewImprovementRepository(session)
    improvement = await repo.get_by_id(improvement_id)
    if not improvement:
        return ""

    ai_client = AIClient()
    try:
        flow = await ai_client.generate_improvement_flow(
            technology_title=improvement.technology_title,
            improvement_summary=improvement.summary,
            vacancy_title=vacancy_title,
            vacancy_description=vacancy_description,
        )
    finally:
        await close_ai_client(ai_client)

    if flow:
        await repo.set_improvement_flow(improvement_id, flow)
        await session.commit()

    return flow


async def update_improvement_status(
    session: AsyncSession,
    improvement_id: int,
    status: str,
) -> None:
    await InterviewImprovementRepository(session).update_status(improvement_id, status)
    await session.commit()


async def bulk_create_questions(
    session: AsyncSession,
    interview_id: int,
    questions: list[dict[str, str]],
) -> None:
    await InterviewQuestionRepository(session).bulk_create(interview_id, questions)
    await session.commit()


def format_vacancy_header(
    vacancy_title: str,
    company_name: str | None,
    experience_level: str | None,
    hh_vacancy_url: str | None,
) -> str:
    lines = [f"<b>🏢 {vacancy_title}</b>"]
    if company_name:
        lines.append(f"Компания: {company_name}")
    if experience_level:
        lines.append(f"Опыт: {experience_level}")
    if hh_vacancy_url:
        lines.append(f'<a href="{hh_vacancy_url}">Открыть на HH.ru</a>')
    return "\n".join(lines)
