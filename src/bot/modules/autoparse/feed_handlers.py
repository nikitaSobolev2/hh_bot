"""Handlers for the interactive vacancy feed."""

from __future__ import annotations

import contextlib

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.modules.autoparse import feed_services
from src.bot.modules.autoparse.callbacks import FeedCallback
from src.core.i18n import I18nContext
from src.models.user import User
from src.models.vacancy_feed import VacancyFeedSession
from src.repositories.autoparse import AutoparsedVacancyRepository

router = Router(name="feed")


def feed_vacancy_keyboard(
    session_id: int,
    vacancy_id: int,
    vacancy_url: str,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("feed-btn-open"),
                    url=vacancy_url,
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("feed-btn-like"),
                    callback_data=FeedCallback(
                        action="like", session_id=session_id, vacancy_id=vacancy_id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=i18n.get("feed-btn-dislike"),
                    callback_data=FeedCallback(
                        action="dislike", session_id=session_id, vacancy_id=vacancy_id
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("feed-btn-show-later"),
                    callback_data=FeedCallback(
                        action="show_later", session_id=session_id, vacancy_id=vacancy_id
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("feed-btn-stop"),
                    callback_data=FeedCallback(action="stop", session_id=session_id).pack(),
                )
            ],
        ]
    )


def feed_start_keyboard(session_id: int, i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("feed-btn-start"),
                    callback_data=FeedCallback(action="start", session_id=session_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("feed-btn-stop"),
                    callback_data=FeedCallback(action="stop", session_id=session_id).pack(),
                )
            ],
        ]
    )


@router.callback_query(FeedCallback.filter(F.action == "start"))
async def handle_feed_start(
    callback: CallbackQuery,
    callback_data: FeedCallback,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    feed_session = await feed_services.get_feed_session(session, callback_data.session_id)
    if not feed_session or feed_session.is_completed:
        await callback.answer(i18n.get("feed-session-not-found"), show_alert=True)
        return

    vacancy_repo = AutoparsedVacancyRepository(session)
    vacancy_id = feed_session.vacancy_ids[feed_session.current_index]
    vacancy = await vacancy_repo.get_by_id(vacancy_id)
    if not vacancy:
        await callback.answer()
        return

    total = len(feed_session.vacancy_ids)
    text = feed_services.build_vacancy_card(vacancy, feed_session.current_index, total, i18n.locale)
    keyboard = feed_vacancy_keyboard(feed_session.id, vacancy.id, vacancy.url, i18n)

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(FeedCallback.filter(F.action.in_({"like", "dislike"})))
async def handle_feed_react(
    callback: CallbackQuery,
    callback_data: FeedCallback,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    feed_session = await feed_services.get_feed_session(session, callback_data.session_id)
    if not feed_session or feed_session.is_completed:
        await callback.answer()
        return

    is_like = callback_data.action == "like"
    await feed_services.record_reaction(session, feed_session, callback_data.vacancy_id, is_like)

    total = len(feed_session.vacancy_ids)
    if feed_session.current_index >= total:
        await _show_results(callback, session, feed_session, i18n)
        return

    vacancy_repo = AutoparsedVacancyRepository(session)
    next_vacancy_id = feed_session.vacancy_ids[feed_session.current_index]
    vacancy = await vacancy_repo.get_by_id(next_vacancy_id)
    if not vacancy:
        await callback.answer()
        return

    text = feed_services.build_vacancy_card(vacancy, feed_session.current_index, total, i18n.locale)
    keyboard = feed_vacancy_keyboard(feed_session.id, vacancy.id, vacancy.url, i18n)

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(FeedCallback.filter(F.action == "show_later"))
async def handle_feed_show_later(
    callback: CallbackQuery,
    callback_data: FeedCallback,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    feed_session = await feed_services.get_feed_session(session, callback_data.session_id)
    if not feed_session or feed_session.is_completed:
        await callback.answer()
        return

    await feed_services.move_vacancy_to_end(session, feed_session)

    total = len(feed_session.vacancy_ids)
    if feed_session.current_index >= total:
        await _show_results(callback, session, feed_session, i18n)
        return

    vacancy_repo = AutoparsedVacancyRepository(session)
    next_vacancy_id = feed_session.vacancy_ids[feed_session.current_index]
    vacancy = await vacancy_repo.get_by_id(next_vacancy_id)
    if not vacancy:
        await callback.answer()
        return

    text = feed_services.build_vacancy_card(vacancy, feed_session.current_index, total, i18n.locale)
    keyboard = feed_vacancy_keyboard(feed_session.id, vacancy.id, vacancy.url, i18n)

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(FeedCallback.filter(F.action == "stop"))
async def handle_feed_stop(
    callback: CallbackQuery,
    callback_data: FeedCallback,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    feed_session = await feed_services.get_feed_session(session, callback_data.session_id)
    if not feed_session:
        await callback.answer()
        return
    await _show_results(callback, session, feed_session, i18n)


async def _show_results(
    callback: CallbackQuery,
    session: AsyncSession,
    feed_session: VacancyFeedSession,
    i18n: I18nContext,
) -> None:
    if not feed_session.is_completed:
        await feed_services.complete_feed_session(session, feed_session)

    vacancy_repo = AutoparsedVacancyRepository(session)
    liked_vacancies = []
    for vid in feed_session.liked_ids:
        vacancy = await vacancy_repo.get_by_id(vid)
        if vacancy:
            liked_vacancies.append(vacancy)

    vacancies_by_id = {v.id: v for v in liked_vacancies}
    results = feed_services.compute_feed_results(feed_session, vacancies_by_id)
    text = feed_services.build_results_message(results, i18n.locale)

    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=None, parse_mode="HTML")
    await callback.answer()
