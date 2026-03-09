"""Pure service functions for the interactive vacancy feed."""

from __future__ import annotations

import html
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.i18n import get_text
from src.models.autoparse import AutoparsedVacancy
from src.models.vacancy_feed import VacancyFeedSession
from src.repositories.vacancy_feed import VacancyFeedSessionRepository

_MAX_DESCRIPTION_LENGTH = 1500
_CURRENCY_MARKERS = frozenset({"₽", "$", "€", "£", "¥", "руб", "rub", "usd", "eur", "₴"})


def _has_currency_marker(salary: str) -> bool:
    lower = salary.lower()
    return any(marker in lower for marker in _CURRENCY_MARKERS)


async def create_feed_session(
    session: AsyncSession,
    user_id: int,
    company_id: int,
    chat_id: int,
    vacancy_ids: list[int],
) -> VacancyFeedSession:
    repo = VacancyFeedSessionRepository(session)
    feed_session = await repo.create(
        user_id=user_id,
        autoparse_company_id=company_id,
        chat_id=chat_id,
        vacancy_ids=vacancy_ids,
        current_index=0,
        liked_ids=[],
        disliked_ids=[],
        is_completed=False,
    )
    await session.commit()
    return feed_session


async def get_feed_session(session: AsyncSession, session_id: int) -> VacancyFeedSession | None:
    repo = VacancyFeedSessionRepository(session)
    return await repo.get_by_id(session_id)


async def record_reaction(
    session: AsyncSession,
    feed_session: VacancyFeedSession,
    vacancy_id: int,
    is_like: bool,
) -> None:
    liked = list(feed_session.liked_ids)
    disliked = list(feed_session.disliked_ids)
    if is_like:
        liked.append(vacancy_id)
    else:
        disliked.append(vacancy_id)
    repo = VacancyFeedSessionRepository(session)
    await repo.update(
        feed_session,
        liked_ids=liked,
        disliked_ids=disliked,
        current_index=feed_session.current_index + 1,
    )
    await session.commit()


async def complete_feed_session(
    session: AsyncSession,
    feed_session: VacancyFeedSession,
) -> None:
    repo = VacancyFeedSessionRepository(session)
    await repo.update(
        feed_session,
        is_completed=True,
        completed_at=datetime.now(UTC).replace(tzinfo=None),
    )
    await session.commit()


def compute_feed_results(
    feed_session: VacancyFeedSession,
    vacancies_by_id: dict[int, AutoparsedVacancy],
) -> dict:
    seen = feed_session.current_index
    total = len(feed_session.vacancy_ids)
    liked_count = len(feed_session.liked_ids)
    disliked_count = len(feed_session.disliked_ids)

    compat_scores = [
        vacancies_by_id[vid].compatibility_score
        for vid in feed_session.liked_ids
        if vid in vacancies_by_id and vacancies_by_id[vid].compatibility_score is not None
    ]
    avg_compat_liked = sum(compat_scores) / len(compat_scores) if compat_scores else None

    return {
        "seen": seen,
        "total": total,
        "liked": liked_count,
        "disliked": disliked_count,
        "avg_compat_liked": avg_compat_liked,
    }


def build_stats_message(
    vacancy_title: str,
    count: int,
    avg_compat: float | None,
    locale: str = "ru",
) -> str:
    lines = [
        f"📥 <b>{html.escape(vacancy_title)}</b>",
        "",
        get_text("feed-stats-count", locale, count=count),
    ]
    if avg_compat is not None:
        lines.append(get_text("feed-stats-avg-compat", locale, avg=f"{avg_compat:.0f}"))
    lines.append("")
    lines.append(get_text("feed-stats-hint", locale))
    return "\n".join(lines)


def build_vacancy_card(
    vacancy: AutoparsedVacancy,
    index: int,
    total: int,
    locale: str = "ru",
) -> str:
    progress = get_text("feed-vacancy-progress", locale, current=index + 1, total=total)
    safe_title = html.escape(vacancy.title)
    lines = [f"{progress} — <b><a href='{vacancy.url}'>{safe_title}</a></b>"]

    if vacancy.company_name:
        lines.append(f"\n🏢 {html.escape(vacancy.company_name)}")

    if vacancy.salary and _has_currency_marker(vacancy.salary):
        lines.append(f"💰 {vacancy.salary}")

    if vacancy.work_experience:
        lines.append(f"🎓 {vacancy.work_experience}")

    if vacancy.employment_type:
        lines.append(f"⏰ {vacancy.employment_type}")

    if vacancy.work_schedule:
        lines.append(f"📅 {vacancy.work_schedule}")

    if vacancy.working_hours:
        lines.append(f"🕗 {vacancy.working_hours}")

    if vacancy.work_formats:
        lines.append(f"📍 {vacancy.work_formats}")

    if vacancy.raw_skills:
        skills_text = (
            ", ".join(vacancy.raw_skills)
            if isinstance(vacancy.raw_skills, list)
            else str(vacancy.raw_skills)
        )
        lines.append(f"🔧 {skills_text}")

    if vacancy.compatibility_score is not None:
        label = get_text("autoparse-compatibility-label", locale)
        lines.append(f"\n🎯 {label}: {vacancy.compatibility_score:.0f}%")

    if vacancy.ai_summary:
        lines.append(f"\n{html.escape(vacancy.ai_summary)}")
    elif vacancy.description:
        truncated = vacancy.description[:_MAX_DESCRIPTION_LENGTH]
        lines.append(f"\n{html.escape(truncated)}")

    return "\n".join(lines)


def build_results_message(results: dict, locale: str = "ru") -> str:
    lines = [
        f"<b>{get_text('feed-results-header', locale)}</b>",
        "",
        get_text("feed-results-seen", locale, seen=results["seen"], total=results["total"]),
        get_text("feed-results-liked", locale, liked=results["liked"]),
        get_text("feed-results-disliked", locale, disliked=results["disliked"]),
    ]
    if results["avg_compat_liked"] is not None:
        avg = f"{results['avg_compat_liked']:.0f}"
        lines.append(get_text("feed-results-avg-liked-compat", locale, avg=avg))
    return "\n".join(lines)
