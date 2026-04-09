"""Celery task for cover letter generation from autoparse vacancy feed."""

from __future__ import annotations

import contextlib
import html
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from src.core.constants import AppSettingKey
from src.core.logging import get_logger
from src.worker.app import celery_app
from src.worker.base_task import HHBotTask
from src.worker.utils import run_async

logger = get_logger(__name__)

if TYPE_CHECKING:
    from src.services.ai.client import AIClient

_AGENT_INTRO_PHRASES = ("Вот сопроводительное", "Составляю", "Вот письмо", "Готово.", "Вот ваш")
COVER_LETTER_DISPLAY_MAX = 2000
TELEGRAM_MESSAGE_MAX = 4096

# Long dash chars (em dash, en dash, etc.) to replace with regular hyphen
_LONG_DASH_CHARS = ("—", "–", "―", "‒", "−")


def _cover_letter_telegram_pre_html(plain: str) -> str:
    """Wrap cover letter in Telegram HTML ``<pre>`` so the client shows copy-friendly text."""
    return f"<pre>{html.escape(plain, quote=False)}</pre>"


def _sanitize_for_telegram(text: str) -> str:
    """Remove control chars and ensure text is valid for Telegram."""
    if not text or not text.strip():
        return ""
    # Strip control characters except newline and tab
    result = "".join(
        c for c in text
        if c in "\n\t" or (ord(c) >= 32 and ord(c) != 0x7F)
    )
    return result[:TELEGRAM_MESSAGE_MAX].strip()


def _normalize_dashes(text: str) -> str:
    """Replace long dash characters with regular hyphen."""
    if not text:
        return text
    result = text
    for char in _LONG_DASH_CHARS:
        result = result.replace(char, "-")
    return result


async def _normalize_dashes_in_token_stream(
    raw_stream: AsyncGenerator[str, None],
) -> AsyncGenerator[str, None]:
    """Normalize long dashes per chunk so streamed Telegram text uses ASCII hyphen."""
    async for chunk in raw_stream:
        yield _normalize_dashes(chunk)


def _strip_agent_wrapper(text: str) -> str:
    """Remove agent intro phrases so only the cover letter content remains.

    Unlike vacancy summary (third-person), cover letters are first-person documents
    where phrases like «Могу подготовить» are natural content (e.g. call to action).
    We only strip leading agent meta-phrases, not potential outro markers that would
    incorrectly truncate legitimate letter content.
    """
    if not text or not text.strip():
        return text
    result = text.strip()

    for phrase in _AGENT_INTRO_PHRASES:
        if result.lower().startswith(phrase.lower()):
            idx = result.find("\n\n")
            if idx > 0:
                result = result[idx + 2 :].lstrip()
            break

    return result.rstrip()


async def generate_cover_letter_plaintext_for_autoparsed_vacancy(
    session_factory,
    user_id: int,
    vacancy_id: int,
    cover_letter_style: str,
    *,
    ai_client: AIClient | None = None,
) -> str:
    """Non-streaming cover letter for an AutoparsedVacancy (shared by feed chain and autorespond API)."""
    from src.bot.modules.autoparse import services as ap_service
    from src.repositories.autoparse import AutoparsedVacancyRepository
    from src.repositories.user import UserRepository
    from src.repositories.work_experience import WorkExperienceRepository
    from src.services.ai.client import AIClient
    from src.services.ai.prompts import (
        WorkExperienceEntry,
        build_cover_letter_system_prompt,
        build_cover_letter_user_content,
    )

    async with session_factory() as session:
        we_repo = WorkExperienceRepository(session)
        raw_experiences = await we_repo.get_active_by_user(user_id)
        vacancy_repo = AutoparsedVacancyRepository(session)
        vacancy = await vacancy_repo.get_by_id(vacancy_id)

    if not vacancy:
        raise ValueError("vacancy_not_found")

    async with session_factory() as session:
        settings = await ap_service.get_user_autoparse_settings(session, user_id)
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
    user_name = (settings.get("user_name") or "").strip()
    if not user_name and user:
        user_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    if not user_name:
        user_name = "Кандидат"
    about_me = (settings.get("about_me") or "").strip()

    experiences = [
        WorkExperienceEntry(
            company_name=e.company_name,
            stack=e.stack,
            title=e.title,
            period=e.period,
            achievements=e.achievements,
            duties=e.duties,
        )
        for e in raw_experiences
    ]

    style = (cover_letter_style or "professional").strip() or "professional"
    client = ai_client or AIClient()
    system_prompt = build_cover_letter_system_prompt(style)
    user_content = build_cover_letter_user_content(
        work_experiences=experiences,
        vacancy_title=vacancy.title,
        company_name=vacancy.company_name,
        vacancy_description=vacancy.description or "",
        user_name=user_name,
        about_me=about_me,
    )
    generated_text = await client.generate_text(
        user_content,
        system_prompt=system_prompt,
        timeout=180,
        max_tokens=400,
        temperature=0.6,
    )
    return _normalize_dashes(_strip_agent_wrapper(generated_text))


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="cover_letter.generate",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=240,
    time_limit=300,
)
def generate_cover_letter_task(
    self,
    user_id: int,
    vacancy_id: int,
    chat_id: int,
    message_id: int,
    locale: str = "ru",
    cover_letter_style: str = "professional",
    session_id: int = 0,
    source: str = "autoparse",
    apply_after: dict | None = None,
    silent_feed: bool = False,
) -> dict:
    return run_async(
        lambda sf: _generate_cover_letter_async(
            self,
            sf,
            user_id,
            vacancy_id,
            chat_id,
            message_id,
            locale,
            cover_letter_style,
            session_id,
            source,
            apply_after,
            silent_feed,
        )
    )


def _truncate_for_display(text: str) -> str:
    """Truncate cover letter to a small, readable display size."""
    if len(text) <= COVER_LETTER_DISPLAY_MAX:
        return text
    return text[: COVER_LETTER_DISPLAY_MAX - 10] + "\n..."


def _build_cover_letter_keyboard(
    session_id: int,
    vacancy_id: int,
    locale: str,
    *,
    standalone: bool = False,
):
    """Build keyboard for cover letter view.

    When standalone: back to list, regenerate.
    When in feed: fits/not-fit, show later, regenerate, back to vacancy.
    """
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.core.i18n import get_text

    if standalone:
        from src.bot.modules.cover_letter.callbacks import CoverLetterCallback

        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=get_text("feed-btn-regenerate-cover-letter", locale),
                        callback_data=CoverLetterCallback(
                            action="regenerate",
                            vacancy_id=vacancy_id,
                            source="standalone",
                        ).pack(),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=get_text("cl-btn-generate-one-more", locale),
                        callback_data=CoverLetterCallback(action="generate_new").pack(),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=get_text("btn-back", locale),
                        callback_data=CoverLetterCallback(action="list").pack(),
                    )
                ],
            ]
        )

    from src.bot.modules.autoparse.callbacks import FeedCallback

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_text("feed-btn-fits-me", locale),
                    callback_data=FeedCallback(
                        action="like",
                        session_id=session_id,
                        vacancy_id=vacancy_id,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=get_text("feed-btn-not-fit", locale),
                    callback_data=FeedCallback(
                        action="dislike",
                        session_id=session_id,
                        vacancy_id=vacancy_id,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=get_text("feed-btn-show-later", locale),
                    callback_data=FeedCallback(
                        action="show_later",
                        session_id=session_id,
                        vacancy_id=vacancy_id,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=get_text("feed-btn-regenerate-cover-letter", locale),
                    callback_data=FeedCallback(
                        action="regenerate_cover_letter",
                        session_id=session_id,
                        vacancy_id=vacancy_id,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=get_text("btn-back", locale),
                    callback_data=FeedCallback(
                        action="back_to_vacancy",
                        session_id=session_id,
                        vacancy_id=vacancy_id,
                    ).pack(),
                ),
            ],
        ]
    )


async def _generate_cover_letter_async(
    task: HHBotTask,
    session_factory,
    user_id: int,
    vacancy_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
    cover_letter_style: str,
    session_id: int,
    source: str = "autoparse",
    apply_after: dict | None = None,
    silent_feed: bool = False,
) -> dict:
    from src.repositories.autoparse import AutoparsedVacancyRepository
    from src.repositories.cover_letter_vacancy import CoverLetterVacancyRepository
    from src.repositories.task import CeleryTaskRepository
    from src.repositories.work_experience import WorkExperienceRepository
    from src.services.ai.client import AIClient
    from src.services.ai.prompts import (
        WorkExperienceEntry,
        build_cover_letter_system_prompt,
        build_cover_letter_user_content,
    )

    enabled = await task.check_enabled(AppSettingKey.TASK_COVER_LETTER_ENABLED, session_factory)
    if not enabled:
        return {"status": "disabled"}

    cb = await task.load_circuit_breaker(
        "cover_letter",
        AppSettingKey.CB_COVER_LETTER_FAILURE_THRESHOLD,
        AppSettingKey.CB_COVER_LETTER_RECOVERY_TIMEOUT,
        session_factory,
    )
    if not cb.is_call_allowed():
        return {"status": "circuit_open"}

    if apply_after:
        ap = apply_after.get("autorespond_progress")
        if ap:
            from src.services.autorespond_progress import is_autorespond_cancelled_sync

            if is_autorespond_cancelled_sync(int(apply_after["chat_id"]), str(ap["task_key"])):
                logger.info(
                    "cover_letter_skipped_autorespond_cancelled",
                    user_id=user_id,
                    vacancy_id=vacancy_id,
                    task_key=ap.get("task_key"),
                )
                return {"status": "cancelled", "vacancy_id": vacancy_id, "locale": locale}

    source = source or "autoparse"
    if apply_after:
        resume_for_key = str(apply_after.get("resume_id") or "")
        idempotency_key = f"cover_letter_feed_apply:{user_id}:{vacancy_id}:{resume_for_key}"
    else:
        idempotency_key = f"cover_letter:{user_id}:{source}:{vacancy_id}"
    async with session_factory() as session:
        if not apply_after:
            existing = await CeleryTaskRepository(session).get_by_idempotency_key(idempotency_key)
            if existing and existing.status == "completed":
                stored_text = (existing.result_data or {}).get("generated_text")
                if stored_text:
                    raw = _truncate_for_display(_normalize_dashes(stored_text))
                    display_text = _sanitize_for_telegram(raw)
                    if not display_text:
                        from src.core.i18n import get_text

                        display_text = get_text("feed-cover-letter-generated", locale)
                    display_text = _cover_letter_telegram_pre_html(display_text)
                    keyboard = _build_cover_letter_keyboard(
                        session_id, vacancy_id, locale, standalone=(source == "standalone")
                    )
                    bot = task.create_bot()
                    try:
                        await task.notify_user(
                            bot,
                            chat_id,
                            message_id,
                            display_text,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                        )
                    finally:
                        await bot.session.close()
                return {"status": "already_completed"}

    async with session_factory() as session:
        we_repo = WorkExperienceRepository(session)
        raw_experiences = await we_repo.get_active_by_user(user_id)
        if source == "standalone":
            vacancy_repo = CoverLetterVacancyRepository(session)
        else:
            vacancy_repo = AutoparsedVacancyRepository(session)
        vacancy = await vacancy_repo.get_by_id(vacancy_id)

    if not vacancy:
        logger.warning("Cover letter: vacancy not found", vacancy_id=vacancy_id)
        return {"status": "vacancy_not_found"}

    from src.bot.modules.autoparse import feed_services
    from src.services.hh.vacancy_public import hh_vacancy_public_preflight

    preflight = await hh_vacancy_public_preflight(vacancy.hh_vacancy_id)
    if preflight.unavailable:
        if apply_after and source != "standalone":
            async with session_factory() as session:
                await feed_services.merge_dislike_vacancy_into_feed_sessions(
                    session,
                    user_id,
                    vacancy.autoparse_company_id,
                    vacancy_id,
                )
        return {
            "status": "skipped",
            "reason": "vacancy_unavailable",
            "vacancy_id": vacancy_id,
            "locale": locale,
        }
    if preflight.requires_employer_test:
        if source != "standalone":
            async with session_factory() as session:
                vac_repo = AutoparsedVacancyRepository(session)
                v = await vac_repo.get_by_id(vacancy_id)
                if v:
                    await vac_repo.update(v, needs_employer_questions=True)
                await session.commit()
        return {
            "status": "skipped",
            "reason": "vacancy_requires_test",
            "vacancy_id": vacancy_id,
            "locale": locale,
        }

    from src.bot.modules.autoparse import services as ap_service
    from src.repositories.user import UserRepository

    async with session_factory() as session:
        settings = await ap_service.get_user_autoparse_settings(session, user_id)
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
    user_name = (settings.get("user_name") or "").strip()
    if not user_name and user:
        user_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    if not user_name:
        user_name = "Кандидат"
    about_me = (settings.get("about_me") or "").strip()

    experiences = [
        WorkExperienceEntry(
            company_name=e.company_name,
            stack=e.stack,
            title=e.title,
            period=e.period,
            achievements=e.achievements,
            duties=e.duties,
        )
        for e in raw_experiences
    ]

    style = (cover_letter_style or "professional").strip() or "professional"

    if apply_after:
        try:
            generated_text = await generate_cover_letter_plaintext_for_autoparsed_vacancy(
                session_factory,
                user_id,
                vacancy_id,
                style,
            )
            cb.record_success()
        except Exception as exc:
            cb.record_failure()
            logger.error(
                "Cover letter generation failed",
                user_id=user_id,
                vacancy_id=vacancy_id,
                error=str(exc),
            )
            ap = apply_after.get("autorespond_progress")
            max_r = int(getattr(task, "max_retries", 0) or 0)
            if ap and getattr(task.request, "retries", 0) >= max_r:
                from src.services.autorespond_progress import tick_autorespond_bar

                tick_bot = task.create_bot()
                try:
                    await tick_autorespond_bar(
                        bot=tick_bot,
                        chat_id=int(apply_after["chat_id"]),
                        task_key=str(ap["task_key"]),
                        total=int(ap["total"]),
                        locale=str(ap.get("locale") or locale),
                        footer_failed_line=None,
                        title=ap.get("title"),
                        celery_task_id=ap.get("celery_task_id"),
                        finish_progress_task=bool(
                            ap.get("finish_progress_task", True)
                        ),
                    )
                finally:
                    await tick_bot.session.close()
            raise
        from src.worker.tasks.hh_ui_apply import apply_to_vacancy_ui_task

        apply_to_vacancy_ui_task.delay(
            apply_after["user_id"],
            apply_after["chat_id"],
            apply_after["message_id"],
            apply_after["locale"],
            apply_after["hh_linked_account_id"],
            apply_after["autoparsed_vacancy_id"],
            apply_after["hh_vacancy_id"],
            apply_after["resume_id"],
            apply_after["vacancy_url"],
            apply_after["feed_session_id"],
            generated_text,
            silent_feed,
            autorespond_progress=apply_after.get("autorespond_progress"),
        )
        if not silent_feed:
            from src.core.i18n import get_text

            bot = task.create_bot()
            try:
                await task.notify_user(
                    bot,
                    chat_id,
                    message_id,
                    get_text("feed-respond-ui-queued", locale),
                    parse_mode="HTML",
                )
            finally:
                await bot.session.close()
        await task.mark_completed(
            idempotency_key,
            "cover_letter",
            user_id,
            session_factory,
            result_data={"generated_text": generated_text, "chained_apply": True},
        )
        return {"status": "completed", "vacancy_id": vacancy_id, "locale": locale}

    ai_client = AIClient()
    system_prompt = build_cover_letter_system_prompt(style)
    user_content = build_cover_letter_user_content(
        work_experiences=experiences,
        vacancy_title=vacancy.title,
        company_name=vacancy.company_name,
        vacancy_description=vacancy.description or "",
        user_name=user_name,
        about_me=about_me,
    )

    keyboard = _build_cover_letter_keyboard(
        session_id, vacancy_id, locale, standalone=(source == "standalone")
    )

    bot = task.create_bot()
    try:
        stream_ok = False
        generated_text = ""
        try:
            from src.services.ai.streaming import stream_to_telegram

            accumulated = await stream_to_telegram(
                bot=bot,
                chat_id=chat_id,
                token_stream=_normalize_dashes_in_token_stream(
                    ai_client.stream_text(
                        user_content,
                        system_prompt=system_prompt,
                        max_tokens=400,
                        temperature=0.6,
                    )
                ),
                initial_text="",
                reply_markup=keyboard,
                html_pre_wrap=True,
            )
            generated_text = _normalize_dashes(_strip_agent_wrapper(accumulated))
            if generated_text.strip():
                stream_ok = True
                cb.record_success()
        except Exception:
            logger.warning(
                "Cover letter streaming failed, falling back to non-streaming API",
            )

        if not stream_ok:
            try:
                generated_text = await ai_client.generate_text(
                    user_content,
                    system_prompt=system_prompt,
                    timeout=180,
                    max_tokens=400,
                    temperature=0.6,
                )
                cb.record_success()
            except Exception as exc:
                cb.record_failure()
                logger.error(
                    "Cover letter generation failed",
                    user_id=user_id,
                    vacancy_id=vacancy_id,
                    error=str(exc),
                )
                raise
            generated_text = _normalize_dashes(_strip_agent_wrapper(generated_text))
            display_text = _sanitize_for_telegram(
                _truncate_for_display(generated_text)
            )
            if not display_text:
                from src.core.i18n import get_text

                display_text = get_text("feed-cover-letter-generated", locale)
            display_text = _cover_letter_telegram_pre_html(display_text)
            await task.notify_user(
                bot,
                chat_id,
                message_id,
                display_text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
        else:
            with contextlib.suppress(Exception):
                await bot.delete_message(chat_id=chat_id, message_id=message_id)

        await task.mark_completed(
            idempotency_key,
            "cover_letter",
            user_id,
            session_factory,
            result_data={"generated_text": generated_text},
        )
        return {"status": "completed", "vacancy_id": vacancy_id, "locale": locale}
    finally:
        await bot.session.close()
