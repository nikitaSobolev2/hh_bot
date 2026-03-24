"""Pure service functions for the interactive vacancy feed."""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.i18n import get_text
from src.models.autoparse import AutoparsedVacancy
from src.models.vacancy_feed import VacancyFeedSession
from src.repositories.vacancy_feed import VacancyFeedSessionRepository

_MAX_DESCRIPTION_LENGTH = 1500
_MAX_FULL_DESCRIPTION_LENGTH = 3000
_TELEGRAM_MESSAGE_LIMIT = 4096
_DESCRIPTION_TRUNCATION_SUFFIX = "… (текст обрезан)"
_CURRENCY_MARKERS = frozenset({"₽", "$", "€", "£", "¥", "руб", "rub", "usd", "eur", "₴"})

# Patterns used by _clean_salary to insert missing spaces in HH.ru salary strings.
_CYRILLIC_BEFORE_DIGIT = re.compile(r"([а-яёА-ЯЁ])(\d)")
_DIGIT_BEFORE_CURRENCY = re.compile(r"(\d)([₽$€£¥₴])")
_CURRENCY_BEFORE_CYRILLIC = re.compile(r"([₽$€£¥₴])([а-яёА-ЯЁ])")
_MULTI_SPACE = re.compile(r" {2,}")


def _has_currency_marker(salary: str) -> bool:
    lower = salary.lower()
    return any(marker in lower for marker in _CURRENCY_MARKERS)


def _clean_salary(salary: str) -> str:
    """Normalise spacing in a raw HH.ru salary string.

    HH.ru sometimes concatenates salary fragments without spaces, producing
    strings like "от4 000$за месяц,до вычета налогов".  This function inserts
    spaces at the obvious boundaries so the result reads naturally.
    """
    text = _CYRILLIC_BEFORE_DIGIT.sub(r"\1 \2", salary)
    text = _DIGIT_BEFORE_CURRENCY.sub(r"\1 \2", text)
    text = _CURRENCY_BEFORE_CYRILLIC.sub(r"\1 \2", text)
    return _MULTI_SPACE.sub(" ", text).strip()


async def create_feed_session(
    session: AsyncSession,
    user_id: int,
    company_id: int,
    chat_id: int,
    vacancy_ids: list[int],
    *,
    hh_linked_account_id: int | None = None,
) -> VacancyFeedSession:
    repo = VacancyFeedSessionRepository(session)
    feed_session = await repo.create(
        user_id=user_id,
        autoparse_company_id=company_id,
        chat_id=chat_id,
        vacancy_ids=vacancy_ids,
        hh_linked_account_id=hh_linked_account_id,
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


def merge_liked_for_respond(
    liked_ids: list[int],
    disliked_ids: list[int],
    vacancy_id: int,
) -> tuple[list[int], list[int]]:
    """Pure merge: ensure vacancy is liked; remove from disliked if present."""
    liked = list(liked_ids or [])
    disliked = list(disliked_ids or [])
    if vacancy_id not in liked:
        liked.append(vacancy_id)
    if vacancy_id in disliked:
        disliked = [x for x in disliked if x != vacancy_id]
    return liked, disliked


def remove_vacancy_from_liked_ids(liked_ids: list[int], vacancy_id: int) -> list[int]:
    """Pure filter: drop vacancy_id from liked list."""
    return [x for x in (liked_ids or []) if x != vacancy_id]


async def ensure_liked_for_respond(
    session: AsyncSession,
    feed_session: VacancyFeedSession,
    vacancy_id: int,
) -> None:
    """Mark vacancy as liked without advancing feed index (respond flows)."""
    liked, disliked = merge_liked_for_respond(
        list(feed_session.liked_ids),
        list(feed_session.disliked_ids),
        vacancy_id,
    )
    repo = VacancyFeedSessionRepository(session)
    await repo.update(
        feed_session,
        liked_ids=liked,
        disliked_ids=disliked,
    )
    await session.commit()


async def remove_liked_on_apply_failure(
    session: AsyncSession,
    feed_session_id: int,
    vacancy_id: int,
) -> None:
    """Remove vacancy from liked_ids when UI apply fails (rollback respond-like)."""
    repo = VacancyFeedSessionRepository(session)
    feed_session = await repo.get_by_id(feed_session_id)
    if not feed_session:
        return
    new_liked = remove_vacancy_from_liked_ids(list(feed_session.liked_ids), vacancy_id)
    if new_liked == list(feed_session.liked_ids):
        return
    await repo.update(feed_session, liked_ids=new_liked)
    await session.commit()


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


async def advance_feed_index(session: AsyncSession, feed_session: VacancyFeedSession) -> None:
    """Increment current_index only (e.g. after queued respond without changing liked/disliked)."""
    repo = VacancyFeedSessionRepository(session)
    await repo.update(
        feed_session,
        current_index=feed_session.current_index + 1,
    )
    await session.commit()


async def move_vacancy_to_end(
    session: AsyncSession,
    feed_session: VacancyFeedSession,
) -> None:
    ids = list(feed_session.vacancy_ids)
    ids.append(ids.pop(feed_session.current_index))
    repo = VacancyFeedSessionRepository(session)
    await repo.update(
        feed_session,
        vacancy_ids=ids,
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
    mode: str = "summary",
) -> str:
    progress = get_text("feed-vacancy-progress", locale, current=index + 1, total=total)
    safe_title = html.escape(vacancy.title)
    lines = [f"{progress} — <b><a href='{vacancy.url}'>{safe_title}</a></b>"]

    if vacancy.company_name:
        lines.append(f"\n🏢 {html.escape(vacancy.company_name)}")

    if vacancy.salary and _has_currency_marker(vacancy.salary):
        lines.append(f"💰 {_clean_salary(vacancy.salary)}")

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

    if getattr(vacancy, "needs_employer_questions", False):
        lines.append(f"\n📝 {get_text('feed-card-employer-questions', locale)}")

    if mode == "description":
        if vacancy.description:
            header_length = len("\n".join(lines))
            available = _TELEGRAM_MESSAGE_LIMIT - header_length - 50
            limit = min(_MAX_FULL_DESCRIPTION_LENGTH, max(available, 500))
            raw = vacancy.description
            if len(raw) > limit:
                raw = raw[:limit] + _DESCRIPTION_TRUNCATION_SUFFIX
            lines.append(f"\n{html.escape(raw)}")
    elif vacancy.ai_summary:
        header_block = "\n".join(lines)
        available = _TELEGRAM_MESSAGE_LIMIT - len(header_block) - 80
        truncation_suffix = get_text("feed-content-truncated", locale)
        raw = html.escape(vacancy.ai_summary)
        if len(raw) > available:
            raw = raw[: available - len(truncation_suffix)] + truncation_suffix
        lines.append(f"\n{raw}")
    elif vacancy.description:
        truncated = vacancy.description[:_MAX_DESCRIPTION_LENGTH]
        lines.append(f"\n{html.escape(truncated)}")

    return "\n".join(lines)


def build_results_message(
    results: dict,
    locale: str = "ru",
    *,
    ui_apply_lines: list[str] | None = None,
) -> str:
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
    text = "\n".join(lines)
    if ui_apply_lines:
        text += "\n\n"
        text += f"<b>{get_text('feed-results-ui-applies-header', locale)}</b>\n"
        text += "\n".join(ui_apply_lines)
    return text


def format_ui_apply_result_line(
    title: str,
    *,
    success: bool,
    detail: str | None,
    status: str | None = None,
    locale: str = "ru",
) -> str:
    safe_title = html.escape(title)
    if success:
        return get_text("feed-results-ui-apply-ok", locale, title=safe_title)
    if status == "needs_employer_questions":
        return get_text("feed-results-ui-apply-employer-questions", locale, title=safe_title)
    d = html.escape(detail or "")
    return get_text("feed-results-ui-apply-err", locale, title=safe_title, detail=d)
