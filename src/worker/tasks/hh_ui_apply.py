"""Celery task: apply to an hh.ru vacancy via Playwright (UI)."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlparse

from aiogram.types import BufferedInputFile
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import settings
from src.core.constants import AppSettingKey
from src.core.i18n import I18nContext, get_text
from src.core.logging import get_logger
from src.repositories.app_settings import AppSettingRepository
from src.repositories.autoparse import AutoparsedVacancyRepository
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


def _coerce_debug_screenshots_flag(raw: object) -> bool:
    if raw is True:
        return True
    if raw is False or raw is None:
        return False
    if isinstance(raw, str):
        return raw.strip().lower() in ("true", "1", "yes")
    return bool(raw)


def _map_outcome_to_status(outcome: ApplyOutcome) -> tuple[str, str | None]:
    """Return (status, error_code) for hh_application_attempts."""
    if outcome == ApplyOutcome.EMPLOYER_QUESTIONS:
        return "needs_employer_questions", "ui:employer_questions"
    if outcome in (ApplyOutcome.SUCCESS, ApplyOutcome.ALREADY_RESPONDED):
        return "success", None if outcome == ApplyOutcome.SUCCESS else f"ui:{outcome.value}"
    if outcome == ApplyOutcome.RATE_LIMITED:
        return "error", "ui:rate_limited"
    if outcome == ApplyOutcome.VACANCY_UNAVAILABLE:
        return "skipped", "ui:vacancy_unavailable"
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
    autorespond_progress: dict | None = None,
) -> dict:
    from src.bot.modules.autoparse import feed_services
    from src.bot.modules.autoparse.feed_handlers import (
        _feed_show_respond_button,
        _feed_vacancy_keyboard_options,
        feed_vacancy_keyboard,
    )
    from src.repositories.autoparse import AutoparsedVacancyRepository
    from src.repositories.vacancy_feed import VacancyFeedSessionRepository
    from src.services.autorespond_progress import is_autorespond_cancelled_sync

    if (
        autorespond_progress
        and autorespond_progress.get("task_key")
        and is_autorespond_cancelled_sync(int(chat_id), str(autorespond_progress["task_key"]))
    ):
        logger.info(
            "hh_ui_apply_skipped_autorespond_cancelled",
            user_id=user_id,
            autoparsed_vacancy_id=autoparsed_vacancy_id,
            task_key=autorespond_progress.get("task_key"),
        )
        return {
            "status": "cancelled",
            "vacancy_id": autoparsed_vacancy_id,
            "reason": "autorespond_cancelled",
        }

    bot = self.create_bot()
    send_error_screenshot_to_user = False
    try:
        cipher = HhTokenCipher(settings.hh_token_encryption_key)

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

            settings_repo = AppSettingRepository(session)
            debug_raw = await settings_repo.get_value(
                AppSettingKey.HH_UI_DEBUG_PLAYWRIGHT_SCREENSHOTS,
                default=False,
            )
            debug_screenshots = _coerce_debug_screenshots_flag(debug_raw)
            send_err_raw = await settings_repo.get_value(
                AppSettingKey.HH_UI_DEBUG_SEND_ERROR_SCREENSHOT_TO_USER,
                default=False,
            )
            send_error_screenshot_to_user = _coerce_debug_screenshots_flag(send_err_raw)
            attach_error_bytes = debug_screenshots or send_error_screenshot_to_user
            config = HhUiApplyConfig.from_settings()
            if debug_screenshots:
                Path(settings.hh_ui_debug_screenshot_dir).mkdir(parents=True, exist_ok=True)
                config = replace(
                    config,
                    debug_screenshot_dir=settings.hh_ui_debug_screenshot_dir,
                )
            if attach_error_bytes:
                config = replace(config, attach_error_screenshot_bytes=True)

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

        from src.services.hh.vacancy_public import hh_vacancy_public_is_unavailable

        if await hh_vacancy_public_is_unavailable(hh_vacancy_id):
            result = ApplyResult(
                outcome=ApplyOutcome.VACANCY_UNAVAILABLE,
                detail="preflight_api",
            )
        else:
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
            detail=(result.detail or "")[:2000] if result.detail else None,
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
            vac_repo = AutoparsedVacancyRepository(session)
            if result.outcome == ApplyOutcome.EMPLOYER_QUESTIONS:
                v_up = await vac_repo.get_by_id(autoparsed_vacancy_id)
                if v_up:
                    await vac_repo.update(v_up, needs_employer_questions=True)
            elif result.outcome in (ApplyOutcome.SUCCESS, ApplyOutcome.ALREADY_RESPONDED):
                v_up = await vac_repo.get_by_id(autoparsed_vacancy_id)
                if v_up and v_up.needs_employer_questions:
                    await vac_repo.update(v_up, needs_employer_questions=False)
            await session.commit()
            logger.info(
                "hh_ui_apply_attempt_recorded",
                task_id=getattr(self.request, "id", None),
                user_id=user_id,
                vacancy_id=autoparsed_vacancy_id,
                status=status,
            )

        if result.outcome == ApplyOutcome.VACANCY_UNAVAILABLE:
            async with session_factory() as s_dis:
                vac_row = await AutoparsedVacancyRepository(s_dis).get_by_id(autoparsed_vacancy_id)
                if feed_session_id and feed_session_id > 0:
                    fr = VacancyFeedSessionRepository(s_dis)
                    fs = await fr.get_by_id(feed_session_id)
                    if fs:
                        await feed_services.record_reaction(
                            s_dis, fs, autoparsed_vacancy_id, False
                        )
                elif vac_row and silent_feed:
                    await feed_services.merge_dislike_vacancy_into_feed_sessions(
                        s_dis,
                        user_id,
                        vac_row.autoparse_company_id,
                        autoparsed_vacancy_id,
                    )
            async with session_factory() as s_reload:
                fr = VacancyFeedSessionRepository(s_reload)
                feed_session = await fr.get_by_id(feed_session_id)
        elif status != "success" and status != "needs_employer_questions":
            async with session_factory() as s_unlike:
                await feed_services.remove_liked_on_apply_failure(
                    s_unlike, feed_session_id, autoparsed_vacancy_id
                )
            async with session_factory() as s_reload:
                fr = VacancyFeedSessionRepository(s_reload)
                feed_session = await fr.get_by_id(feed_session_id)

        async with session_factory() as s_vac:
            vac_repo = AutoparsedVacancyRepository(s_vac)
            v_fresh = await vac_repo.get_by_id(autoparsed_vacancy_id)
            if v_fresh:
                vacancy = v_fresh

        if silent_feed:
            if (
                send_error_screenshot_to_user
                and result.screenshot_bytes
                and status != "success"
            ):
                err_name = (
                    "hh_captcha.png"
                    if result.outcome == ApplyOutcome.CAPTCHA
                    else "hh_apply_error.png"
                )
                with contextlib.suppress(Exception):
                    await bot.send_photo(
                        chat_id,
                        BufferedInputFile(result.screenshot_bytes, err_name),
                    )
            return {"status": status, "outcome": result.outcome.value}

        i18n = I18nContext(locale)

        if result.outcome == ApplyOutcome.VACANCY_UNAVAILABLE:
            if feed_session_id and feed_session:
                total = len(feed_session.vacancy_ids)
                if feed_session.current_index < total:
                    next_vid = feed_session.vacancy_ids[feed_session.current_index]
                    async with session_factory() as s_next:
                        next_vac = await AutoparsedVacancyRepository(s_next).get_by_id(next_vid)
                    if next_vac:
                        text = feed_services.build_vacancy_card(
                            next_vac, feed_session.current_index, total, locale
                        )
                        text = f"{text}\n\n{get_text('feed-respond-vacancy-unavailable', locale)}"
                        keyboard = feed_vacancy_keyboard(
                            feed_session.id,
                            next_vac.id,
                            next_vac.url,
                            i18n,
                            current_index=feed_session.current_index,
                            show_respond=_feed_show_respond_button(feed_session),
                            **_feed_vacancy_keyboard_options(feed_session, next_vac.id),
                        )
                        await self.notify_user(
                            bot,
                            chat_id,
                            message_id,
                            text,
                            reply_markup=keyboard,
                        )
                        return {"status": status, "outcome": result.outcome.value}
                await self.notify_user(
                    bot,
                    chat_id,
                    message_id,
                    get_text("feed-respond-vacancy-unavailable-feed-end", locale),
                )
                return {"status": status, "outcome": result.outcome.value}
            await self.notify_user(
                bot,
                chat_id,
                message_id,
                get_text("feed-respond-vacancy-unavailable", locale),
            )
            return {"status": status, "outcome": result.outcome.value}

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
        elif result.outcome == ApplyOutcome.EMPLOYER_QUESTIONS:
            text = f"{text}\n\n{get_text('feed-respond-employer-questions', locale)}"
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
        elif (
            send_error_screenshot_to_user
            and result.screenshot_bytes
            and status != "success"
            and result.outcome != ApplyOutcome.CAPTCHA
        ):
            with contextlib.suppress(Exception):
                await bot.send_photo(
                    chat_id,
                    BufferedInputFile(result.screenshot_bytes, "hh_apply_error.png"),
                )

        return {"status": status, "outcome": result.outcome.value}
    finally:
        if autorespond_progress and autorespond_progress.get("task_key"):
            with contextlib.suppress(Exception):
                from src.services.autorespond_progress import tick_autorespond_bar

                await tick_autorespond_bar(
                    bot=bot,
                    chat_id=chat_id,
                    task_key=str(autorespond_progress["task_key"]),
                    total=int(autorespond_progress["total"]),
                    locale=str(autorespond_progress.get("locale") or locale),
                    footer_failed_line=None,
                )
        with contextlib.suppress(Exception):
            await bot.session.close()


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="hh_ui.apply_to_vacancy",
    # Dedicated Celery queue so only ``hh_ui`` workers run Playwright (see docker-compose
    # ``celery_worker_hh_ui``). Avoids N general workers each spawning Chromium and OOMing small VMs.
    queue="hh_ui",
    # Hard limit: worker child gets SIGKILL after ``time_limit`` (see Celery docs). Tune via
    # ``HH_UI_APPLY_TASK_TIME_LIMIT`` / ``HH_UI_APPLY_TASK_SOFT_TIME_LIMIT`` when hh.ru or Playwright runs slow.
    soft_time_limit=settings.hh_ui_apply_task_soft_time_limit,
    time_limit=settings.hh_ui_apply_task_time_limit,
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
    autorespond_progress: dict | None = None,
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
            autorespond_progress=autorespond_progress,
        )
    )
