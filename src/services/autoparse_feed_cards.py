from __future__ import annotations

import html
from collections.abc import Sequence

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.modules.autoparse.callbacks import AutoparseCallback, FeedCallback
from src.core.i18n import get_text


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


def build_feed_stats_markup(
    *,
    feed_session_id: int,
    locale: str,
    linked_accounts: Sequence | None = None,
    back_action: str = "hub",
) -> InlineKeyboardMarkup:
    linked_accounts = linked_accounts or []
    if len(linked_accounts) > 1:
        rows: list[list[InlineKeyboardButton]] = []
        for acc in linked_accounts:
            label = (acc.label or acc.hh_user_id)[:40]
            rows.append(
                [
                    InlineKeyboardButton(
                        text=label,
                        callback_data=FeedCallback(
                            action="pick_hh_account",
                            session_id=feed_session_id,
                            hh_account_id=acc.id,
                        ).pack(),
                    )
                ]
            )
        rows.append(
            [
                InlineKeyboardButton(
                    text=get_text("btn-back", locale),
                    callback_data=AutoparseCallback(action=back_action).pack(),
                )
            ]
        )
        return InlineKeyboardMarkup(inline_keyboard=rows)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_text("feed-btn-start", locale),
                    callback_data=FeedCallback(action="start", session_id=feed_session_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_text("feed-btn-stop", locale),
                    callback_data=FeedCallback(action="stop", session_id=feed_session_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_text("btn-back", locale),
                    callback_data=AutoparseCallback(action=back_action).pack(),
                )
            ],
        ]
    )


def build_feed_stats_card(
    *,
    vacancy_title: str,
    vacancies: Sequence,
    feed_session_id: int,
    locale: str,
    linked_accounts: Sequence | None = None,
    back_action: str = "hub",
) -> tuple[str, InlineKeyboardMarkup]:
    compat_scores = [v.compatibility_score for v in vacancies if v.compatibility_score is not None]
    avg_compat = sum(compat_scores) / len(compat_scores) if compat_scores else None

    text = build_stats_message(vacancy_title, len(vacancies), avg_compat, locale)
    if linked_accounts and len(linked_accounts) > 1:
        text = f"{text}\n\n{get_text('feed-pick-hh-hint', locale)}"

    keyboard = build_feed_stats_markup(
        feed_session_id=feed_session_id,
        locale=locale,
        linked_accounts=linked_accounts,
        back_action=back_action,
    )
    return text, keyboard


async def send_feed_stats_card(
    *,
    bot_token: str,
    chat_id: int,
    vacancy_title: str,
    vacancies: Sequence,
    feed_session_id: int,
    locale: str,
    linked_accounts: Sequence | None = None,
    back_action: str = "hub",
) -> None:
    text, keyboard = build_feed_stats_card(
        vacancy_title=vacancy_title,
        vacancies=vacancies,
        feed_session_id=feed_session_id,
        locale=locale,
        linked_accounts=linked_accounts,
        back_action=back_action,
    )
    bot = Bot(
        token=bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    finally:
        await bot.session.close()


async def create_feed_session(
    session: AsyncSession,
    *,
    user_id: int,
    company_id: int,
    chat_id: int,
    vacancy_ids: list[int],
    hh_linked_account_id: int | None = None,
) -> int:
    from src.repositories.vacancy_feed import VacancyFeedSessionRepository

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
    return feed_session.id
