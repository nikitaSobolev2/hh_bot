"""Celery task: apply to an hh.ru vacancy via Playwright (UI)."""

from __future__ import annotations

import asyncio
import contextlib
from urllib.parse import urlparse

from aiogram.types import BufferedInputFile
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import settings
from src.core.i18n import I18nContext, get_text
from src.core.logging import get_logger
from src.repositories.hh_application_attempt import HhApplicationAttemptRepository
from src.repositories.hh_linked_account import HhLinkedAccountRepository
from src.services.hh.crypto import HhTokenCipher
from src.services.hh_ui.config import HhUiApplyConfig
from src.services.hh_ui.outcomes import ApplyOutcome, ApplyResult
from src.services.hh_ui.runner import apply_to_vacancy_ui, normalize_hh_vacancy_url
from src.services.hh_ui.storage import decrypt_browser_storage
from src.worker.app import celery_app
from src.worker.base_task import HHBotTask
from src.worker.utils import run_async

logger = get_logger(__name__)


def _vacancy_url_safe_for_log(url: str) -> str | None:
    if not url.startswith("https://"):
        return None
    try:
        p = urlparse(url)
        if not p.netloc:
            return None
        return f"{p.scheme}://{p.netloc}{p.path}"
    except Exception:
        return None


def _map_outcome_to_status(outcome: ApplyOutcome) -> tuple[str, str | None]:
    """Return (status, error_code) for hh_application_attempts."""
    if outcome in (ApplyOutcome.SUCCESS, ApplyOutcome.ALREADY_RESPONDED):
        return "success", None if outcome == ApplyOutcome.SUCCESS else f"ui:{outcome.value}"
    if outcome == ApplyOutcome.RATE_LIMITED:
        return "error", "ui:rate_limited"
    return "error", f"ui:{outcome.value}"


async def _apply_ui_async(
    self,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
    hh_linked_account_id: int,
    autoparsed_vacancy_id: int,
    hh_vacancy_id: str,
    resume_id: str,
    vacancy_url: str,
    feed_session_id: int,
    cover_letter: str = "",
    *,
    silent_feed: bool = False,
) -> dict:
    from src.bot.modules.autoparse import feed_services
    from src.bot.modules.autoparse.feed_handlers import (
        _feed_show_respond_button,
        _feed_vacancy_keyboard_options,
        feed_vacancy_keyboard,
    )
    from src.repositories.autoparse import AutoparsedVacancyRepository
    from src.repositories.vacancy_feed import VacancyFeedSessionRepository

    bot = self.create_bot()
    try:
        cipher = HhTokenCipher(settings.hh_token_encryption_key)
        config = HhUiApplyConfig.from_settings()

        async with session_factory() as session:
            acc_repo = HhLinkedAccountRepository(session)
            acc = await acc_repo.get_by_id(hh_linked_account_id)
            if not acc or not acc.browser_storage_enc:
                logger.warning(
                    "hh_ui apply: missing browser session",
                    account_id=hh_linked_account_id,
                )
                if not silent_feed:
                    await self.notify_user(
                        bot,
                        chat_id,
                        message_id,
                        get_text("feed-respond-ui-no-session", locale),
                    )
                async with session_factory() as s2:
                    await feed_services.remove_liked_on_apply_failure(
                        s2, feed_session_id, autoparsed_vacancy_id
                    )
                return {"status": "error", "reason": "no_browser_session"}

            storage = decrypt_browser_storage(acc.browser_storage_enc, cipher)
            if not storage:
                if not silent_feed:
                    await self.notify_user(
                        bot,
                        chat_id,
                        message_id,
                        get_text("feed-respond-ui-no-session", locale),
                    )
                async with session_factory() as s2:
                    await feed_services.remove_liked_on_apply_failure(
                        s2, feed_session_id, autoparsed_vacancy_id
                    )
                return {"status": "error", "reason": "decrypt_failed"}

            vac_repo = AutoparsedVacancyRepository(session)
            vacancy = await vac_repo.get_by_id(autoparsed_vacancy_id)
            feed_repo = VacancyFeedSessionRepository(session)
            feed_session = await feed_repo.get_by_id(feed_session_id)

        url = normalize_hh_vacancy_url(
            vacancy_url or (vacancy.url if vacancy else None),
            hh_vacancy_id,
        )
        logger.info(
            "hh_ui_apply_task_start",
            task_id=getattr(self.request, "id", None),
            user_id=user_id,
            vacancy_id=autoparsed_vacancy_id,
            hh_linked_account_id=hh_linked_account_id,
            resume_id_prefix=(resume_id[:12] if resume_id else None),
            vacancy_url_safe=_vacancy_url_safe_for_log(url),
        )

        try:
            result = await asyncio.to_thread(
                apply_to_vacancy_ui,
                storage_state=storage,
                vacancy_url=url,
                resume_hh_id=resume_id,
                config=config,
                log_user_id=user_id,
                cover_letter=cover_letter or "",
            )
        except Exception as exc:
            logger.exception("hh_ui apply failed", error=str(exc))
            result = ApplyResult(outcome=ApplyOutcome.ERROR, detail=str(exc)[:500])

        logger.info(
            "hh_ui_apply_finished",
            task_id=getattr(self.request, "id", None),
            user_id=user_id,
            vacancy_id=autoparsed_vacancy_id,
            outcome=result.outcome.value,
            detail=(result.detail or "")[:200] if result.detail else None,
        )

        status, err_code = _map_outcome_to_status(result.outcome)
        excerpt = (result.detail or "")[:2000]
        if result.screenshot_bytes:
            excerpt = f"{excerpt}\n[screenshot omitted {len(result.screenshot_bytes)}b]"

        async with session_factory() as session:
            attempt_repo = HhApplicationAttemptRepository(session)
            await attempt_repo.create(
                user_id=user_id,
                hh_linked_account_id=hh_linked_account_id,
                autoparsed_vacancy_id=autoparsed_vacancy_id,
                hh_vacancy_id=hh_vacancy_id,
                resume_id=resume_id,
                status=status,
                api_negotiation_id=None,
                error_code=err_code,
                response_excerpt=excerpt or None,
            )
            await session.commit()
            logger.info(
                "hh_ui_apply_attempt_recorded",
                task_id=getattr(self.request, "id", None),
                user_id=user_id,
                vacancy_id=autoparsed_vacancy_id,
                status=status,
            )

        if status != "success":
            async with session_factory() as s_unlike:
                await feed_services.remove_liked_on_apply_failure(
                    s_unlike, feed_session_id, autoparsed_vacancy_id
                )
            async with session_factory() as s_reload:
                fr = VacancyFeedSessionRepository(s_reload)
                feed_session = await fr.get_by_id(feed_session_id)

        if silent_feed:
            return {"status": status, "outcome": result.outcome.value}

        i18n = I18nContext(locale)

        if not vacancy or not feed_session:
            await self.notify_user(
                bot,
                chat_id,
                message_id,
                get_text("feed-respond-ui-task-result", locale, outcome=result.outcome.value),
            )
            return {"status": status, "outcome": result.outcome.value}

        total = len(feed_session.vacancy_ids)
        text = feed_services.build_vacancy_card(
            vacancy, feed_session.current_index, total, locale
        )
        if status == "success":
            text = f"{text}\n\n{get_text('feed-respond-success', locale)}"
        elif result.outcome == ApplyOutcome.CAPTCHA:
            text = f"{text}\n\n{get_text('feed-respond-ui-captcha', locale)}"
        else:
            detail = err_code or result.outcome.value
            text = f"{text}\n\n{get_text('feed-respond-error', locale, detail=detail)}"

        keyboard = feed_vacancy_keyboard(
            feed_session.id,
            vacancy.id,
            vacancy.url,
            i18n,
            current_index=feed_session.current_index,
            show_respond=_feed_show_respond_button(feed_session),
            **_feed_vacancy_keyboard_options(feed_session, vacancy.id),
        )

        await self.notify_user(
            bot,
            chat_id,
            message_id,
            text,
            reply_markup=keyboard,
        )

        if result.outcome == ApplyOutcome.CAPTCHA and result.screenshot_bytes:
            with contextlib.suppress(Exception):
                await bot.send_photo(
                    chat_id,
                    BufferedInputFile(result.screenshot_bytes, "hh_captcha.png"),
                )

        return {"status": status, "outcome": result.outcome.value}
    finally:
        with contextlib.suppress(Exception):
            await bot.session.close()


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="hh_ui.apply_to_vacancy",
    soft_time_limit=360,
    time_limit=420,
)
def apply_to_vacancy_ui_task(
    self,
    user_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
    hh_linked_account_id: int,
    autoparsed_vacancy_id: int,
    hh_vacancy_id: str,
    resume_id: str,
    vacancy_url: str,
    feed_session_id: int,
    cover_letter: str = "",
    silent_feed: bool = False,
) -> dict:
    return run_async(
        lambda sf: _apply_ui_async(
            self,
            sf,
            user_id,
            chat_id,
            message_id,
            locale,
            hh_linked_account_id,
            autoparsed_vacancy_id,
            hh_vacancy_id,
            resume_id,
            vacancy_url,
            feed_session_id,
            cover_letter,
            silent_feed=silent_feed,
        )
    )
