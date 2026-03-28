"""Celery task: apply to an hh.ru vacancy via Playwright (UI)."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import replace
from pathlib import Path
from typing import Any
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
from src.services.hh_ui.runner import (
    VacancyApplySpec,
    apply_to_vacancies_ui_batch,
    normalize_hh_vacancy_url,
)
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
    """Return (status, error_code) for hh_application_attempts.

    Terminal without retry (runner): SUCCESS, ALREADY_RESPONDED, EMPLOYER_QUESTIONS,
    VACANCY_UNAVAILABLE. Retryable: ERROR, RATE_LIMITED, NO_APPLY_BUTTON, SESSION_EXPIRED.
    CAPTCHA is terminal (no automated retry).
    """
    if outcome == ApplyOutcome.EMPLOYER_QUESTIONS:
        return "needs_employer_questions", "ui:employer_questions"
    if outcome in (ApplyOutcome.SUCCESS, ApplyOutcome.ALREADY_RESPONDED):
        return "success", None if outcome == ApplyOutcome.SUCCESS else f"ui:{outcome.value}"
    if outcome == ApplyOutcome.RATE_LIMITED:
        return "error", "ui:rate_limited"
    if outcome == ApplyOutcome.VACANCY_UNAVAILABLE:
        return "skipped", "ui:vacancy_unavailable"
    return "error", f"ui:{outcome.value}"


def _ui_outcome_increments_autorespond_failed(outcome: ApplyOutcome) -> bool:
    """Redis footer: count everything except clear success / already applied / preflight unavailable."""
    return outcome not in (
        ApplyOutcome.SUCCESS,
        ApplyOutcome.ALREADY_RESPONDED,
        ApplyOutcome.VACANCY_UNAVAILABLE,
    )


async def _persist_ui_apply_attempt_and_feed_effects(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: int,
    hh_linked_account_id: int,
    autoparsed_vacancy_id: int,
    hh_vacancy_id: str,
    resume_id: str,
    feed_session_id: int,
    result: ApplyResult,
    silent_feed: bool = False,
) -> tuple[str, str | None]:
    from src.bot.modules.autoparse import feed_services
    from src.repositories.autoparse import AutoparsedVacancyRepository
    from src.repositories.vacancy_feed import VacancyFeedSessionRepository

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

    if result.outcome == ApplyOutcome.VACANCY_UNAVAILABLE:
        async with session_factory() as s_dis:
            vac_row = await AutoparsedVacancyRepository(s_dis).get_by_id(autoparsed_vacancy_id)
            if feed_session_id and feed_session_id > 0:
                fr = VacancyFeedSessionRepository(s_dis)
                fs = await fr.get_by_id(feed_session_id)
                if fs:
                    await feed_services.record_reaction(s_dis, fs, autoparsed_vacancy_id, False)
            elif vac_row and silent_feed:
                await feed_services.merge_dislike_vacancy_into_feed_sessions(
                    s_dis,
                    user_id,
                    vac_row.autoparse_company_id,
                    autoparsed_vacancy_id,
                )
    elif status != "success" and status != "needs_employer_questions":
        async with session_factory() as s_unlike:
            await feed_services.remove_liked_on_apply_failure(
                s_unlike, feed_session_id, autoparsed_vacancy_id
            )

    return status, err_code


_FINALIZE_BATCH_ITEM_THREADSAFE_TIMEOUT_S = 300


async def _notify_negotiations_limit_exceeded(
    bot: Any,
    chat_id: int,
    locale: str,
    autorespond_progress: dict | None,
) -> None:
    """HH account hit active-response limit; notify user and stop autorespond progress if any."""
    msg = get_text("hh-ui-negotiations-limit-notice", locale)
    with contextlib.suppress(Exception):
        await bot.send_message(chat_id, msg)
    if not autorespond_progress or not autorespond_progress.get("task_key"):
        return
    task_key = str(autorespond_progress["task_key"])
    from src.services.autorespond_progress import (
        clear_autorespond_done_counter,
        clear_autorespond_failed_counter,
        clear_hh_ui_batch_checkpoint_sync,
        set_autorespond_cancelled,
    )
    from src.services.progress_service import ProgressService, create_progress_redis

    await set_autorespond_cancelled(chat_id, task_key)
    clear_hh_ui_batch_checkpoint_sync(chat_id, task_key)
    await clear_autorespond_done_counter(chat_id, task_key)
    await clear_autorespond_failed_counter(chat_id, task_key)
    redis = create_progress_redis()
    try:
        svc = ProgressService(bot, chat_id, redis, locale)
        await svc.finish_task(
            task_key,
            shortage_note=get_text("hh-ui-negotiations-limit-shortage", locale),
            complete_bars=True,
        )
    finally:
        await redis.aclose()


async def _finalize_batch_item_async(
    *,
    self,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: int,
    chat_id: int,
    locale: str,
    hh_linked_account_id: int,
    feed_session_id: int,
    it: dict,
    result: ApplyResult,
    items: list[dict],
    finalized_vids: set[int],
    bot: Any,
    silent_feed: bool,
    send_error_screenshot_to_user: bool,
    autorespond_progress: dict | None,
    resume_blob: dict | None = None,
    skip_progress_tick: bool = False,
    skip_persist: bool = False,
) -> None:
    """Persist one batch row, tick autorespond bar, optional screenshot, Redis checkpoint."""
    from src.services.autorespond_progress import (
        increment_autorespond_failed_sync,
        save_hh_ui_batch_checkpoint_sync,
        tick_autorespond_bar,
    )

    vid = int(it["autoparsed_vacancy_id"])
    resume_id = str(it["resume_id"])
    hh_id = str(it["hh_vacancy_id"])
    finalized_vids.add(vid)

    if not skip_persist:
        await _persist_ui_apply_attempt_and_feed_effects(
            session_factory=session_factory,
            user_id=user_id,
            hh_linked_account_id=hh_linked_account_id,
            autoparsed_vacancy_id=vid,
            hh_vacancy_id=hh_id,
            resume_id=resume_id,
            feed_session_id=feed_session_id,
            result=result,
            silent_feed=silent_feed,
        )
    logger.info(
        "hh_ui_apply_batch_item_done",
        task_id=getattr(self.request, "id", None),
        user_id=user_id,
        vacancy_id=vid,
        outcome=result.outcome.value,
        skip_persist=skip_persist,
    )

    task_key = (
        str(autorespond_progress["task_key"])
        if autorespond_progress and autorespond_progress.get("task_key")
        else None
    )
    if task_key:
        with contextlib.suppress(Exception):
            if not skip_progress_tick:
                if _ui_outcome_increments_autorespond_failed(result.outcome):
                    increment_autorespond_failed_sync(int(chat_id), task_key, 1)
                await tick_autorespond_bar(
                    bot=bot,
                    chat_id=chat_id,
                    task_key=task_key,
                    total=int(autorespond_progress["total"]),
                    locale=str(autorespond_progress.get("locale") or locale),
                    footer_failed_line=None,
                    title=autorespond_progress.get("title"),
                    celery_task_id=autorespond_progress.get("celery_task_id"),
                )
        remaining = [
            x
            for x in items
            if int(x["autoparsed_vacancy_id"]) not in finalized_vids
        ]
        save_hh_ui_batch_checkpoint_sync(
            chat_id, task_key, remaining, resume=resume_blob
        )

    if (
        silent_feed
        and send_error_screenshot_to_user
        and result.screenshot_bytes
        and _map_outcome_to_status(result.outcome)[0] != "success"
        and result.outcome != ApplyOutcome.SESSION_EXPIRED
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


async def _apply_batch_ui_async(
    self,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
    hh_linked_account_id: int,
    feed_session_id: int,
    items: list[dict],
    cover_letter_style: str,
    cover_task_enabled: bool,
    silent_feed: bool = True,
    autorespond_progress: dict | None = None,
) -> dict:
    """Apply to several vacancies in one Playwright session (autorespond batch)."""
    from src.bot.modules.autoparse import feed_services
    from src.services.autorespond_progress import (
        hh_ui_batch_resume_payload,
        is_autorespond_cancelled_sync,
        save_hh_ui_batch_checkpoint_sync,
    )
    from src.worker.tasks.cover_letter import generate_cover_letter_plaintext_for_autoparsed_vacancy

    if (
        autorespond_progress
        and autorespond_progress.get("task_key")
        and is_autorespond_cancelled_sync(int(chat_id), str(autorespond_progress["task_key"]))
    ):
        return {"status": "cancelled", "reason": "autorespond_cancelled", "count": len(items)}

    bot = self.create_bot()
    try:
        cipher = HhTokenCipher(settings.hh_token_encryption_key)

        async with session_factory() as session:
            acc_repo = HhLinkedAccountRepository(session)
            acc = await acc_repo.get_by_id(hh_linked_account_id)
            if not acc or not acc.browser_storage_enc:
                logger.warning(
                    "hh_ui batch: missing browser session",
                    account_id=hh_linked_account_id,
                )
                for it in items:
                    with contextlib.suppress(Exception):
                        async with session_factory() as s2:
                            await feed_services.remove_liked_on_apply_failure(
                                s2, feed_session_id, int(it["autoparsed_vacancy_id"])
                            )
                return {"status": "error", "reason": "no_browser_session"}

            storage = decrypt_browser_storage(acc.browser_storage_enc, cipher)
            if not storage:
                for it in items:
                    with contextlib.suppress(Exception):
                        async with session_factory() as s2:
                            await feed_services.remove_liked_on_apply_failure(
                                s2, feed_session_id, int(it["autoparsed_vacancy_id"])
                            )
                return {"status": "error", "reason": "decrypt_failed"}

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

        from src.services.ai.client import AIClient

        cover_ai: AIClient | None = None
        from src.services.hh.vacancy_public import hh_vacancy_public_is_unavailable

        item_by_vid: dict[int, dict] = {int(x["autoparsed_vacancy_id"]): x for x in items}
        finalized_vids: set[int] = set()
        task_key = (
            str(autorespond_progress["task_key"])
            if autorespond_progress and autorespond_progress.get("task_key")
            else None
        )
        resume_blob = (
            hh_ui_batch_resume_payload(
                user_id=user_id,
                chat_id=chat_id,
                message_id=message_id,
                locale=locale,
                hh_linked_account_id=hh_linked_account_id,
                feed_session_id=feed_session_id,
                cover_letter_style=cover_letter_style,
                cover_task_enabled=cover_task_enabled,
                silent_feed=silent_feed,
                autorespond_progress=autorespond_progress,
            )
            if task_key
            else None
        )
        if task_key:
            save_hh_ui_batch_checkpoint_sync(
                chat_id, task_key, list(items), resume=resume_blob
            )

        if task_key and autorespond_progress:
            from src.services.autorespond_progress import (
                ensure_autorespond_progress_task_state_if_missing,
            )

            await ensure_autorespond_progress_task_state_if_missing(
                bot=bot,
                chat_id=int(chat_id),
                autorespond_progress=autorespond_progress,
                locale=locale,
            )

        specs: list[VacancyApplySpec] = []

        for it in items:
            vid = int(it["autoparsed_vacancy_id"])
            hh_id = str(it["hh_vacancy_id"])
            url = normalize_hh_vacancy_url(str(it.get("vacancy_url") or ""), hh_id)
            if await hh_vacancy_public_is_unavailable(hh_id):
                await _finalize_batch_item_async(
                    self=self,
                    session_factory=session_factory,
                    user_id=user_id,
                    chat_id=chat_id,
                    locale=locale,
                    hh_linked_account_id=hh_linked_account_id,
                    feed_session_id=feed_session_id,
                    it=it,
                    result=ApplyResult(
                        outcome=ApplyOutcome.VACANCY_UNAVAILABLE,
                        detail="preflight_api",
                    ),
                    items=items,
                    finalized_vids=finalized_vids,
                    bot=bot,
                    silent_feed=silent_feed,
                    send_error_screenshot_to_user=send_error_screenshot_to_user,
                    autorespond_progress=autorespond_progress,
                    resume_blob=resume_blob,
                )
                continue
            letter = ""
            if cover_task_enabled:
                if cover_ai is None:
                    cover_ai = AIClient()
                try:
                    letter = await generate_cover_letter_plaintext_for_autoparsed_vacancy(
                        session_factory,
                        user_id,
                        vid,
                        cover_letter_style,
                        ai_client=cover_ai,
                    )
                except Exception as exc:
                    logger.warning(
                        "hh_ui_batch_cover_letter_failed",
                        user_id=user_id,
                        vacancy_id=vid,
                        error=str(exc)[:300],
                    )
                    await _finalize_batch_item_async(
                        self=self,
                        session_factory=session_factory,
                        user_id=user_id,
                        chat_id=chat_id,
                        locale=locale,
                        hh_linked_account_id=hh_linked_account_id,
                        feed_session_id=feed_session_id,
                        it=it,
                        result=ApplyResult(
                            outcome=ApplyOutcome.ERROR,
                            detail=f"cover_letter:{exc}"[:500],
                        ),
                        items=items,
                        finalized_vids=finalized_vids,
                        bot=bot,
                        silent_feed=silent_feed,
                        send_error_screenshot_to_user=send_error_screenshot_to_user,
                        autorespond_progress=autorespond_progress,
                        resume_blob=resume_blob,
                    )
                    continue
            specs.append(
                VacancyApplySpec(
                    autoparsed_vacancy_id=vid,
                    hh_vacancy_id=hh_id,
                    vacancy_url=url,
                    resume_hh_id=str(it["resume_id"]),
                    cover_letter=letter,
                )
            )

        loop = asyncio.get_running_loop()

        def _on_playwright_item_done(spec: VacancyApplySpec, result: ApplyResult) -> None:
            it_row = item_by_vid[spec.autoparsed_vacancy_id]
            fut = asyncio.run_coroutine_threadsafe(
                _finalize_batch_item_async(
                    self=self,
                    session_factory=session_factory,
                    user_id=user_id,
                    chat_id=chat_id,
                    locale=locale,
                    hh_linked_account_id=hh_linked_account_id,
                    feed_session_id=feed_session_id,
                    it=it_row,
                    result=result,
                    items=items,
                    finalized_vids=finalized_vids,
                    bot=bot,
                    silent_feed=silent_feed,
                    send_error_screenshot_to_user=send_error_screenshot_to_user,
                    autorespond_progress=autorespond_progress,
                    resume_blob=resume_blob,
                ),
                loop,
            )
            fut.result(timeout=_FINALIZE_BATCH_ITEM_THREADSAFE_TIMEOUT_S)

        abort_reason: str | None = None
        if specs:

            def _cancel_check_sync() -> bool:
                if not autorespond_progress or not autorespond_progress.get("task_key"):
                    return False
                from src.services.autorespond_progress import is_autorespond_cancelled_sync

                return is_autorespond_cancelled_sync(
                    int(chat_id), str(autorespond_progress["task_key"])
                )

            def _run_batch():
                return apply_to_vacancies_ui_batch(
                    storage_state=storage,
                    items=specs,
                    config=config,
                    log_user_id=user_id,
                    max_retries=settings.hh_ui_apply_max_retries,
                    retry_initial_seconds=settings.hh_ui_apply_retry_initial_seconds,
                    retry_delay_cap_seconds=settings.hh_ui_apply_retry_delay_cap_seconds,
                    on_item_done=_on_playwright_item_done,
                    cancel_check=_cancel_check_sync,
                )

            try:
                _, abort_reason = await asyncio.to_thread(_run_batch)
            except Exception as exc:
                logger.exception("hh_ui batch apply failed", error=str(exc))
                err = ApplyResult(outcome=ApplyOutcome.ERROR, detail=str(exc)[:500])
                for s in specs:
                    if s.autoparsed_vacancy_id not in finalized_vids:
                        await _finalize_batch_item_async(
                            self=self,
                            session_factory=session_factory,
                            user_id=user_id,
                            chat_id=chat_id,
                            locale=locale,
                            hh_linked_account_id=hh_linked_account_id,
                            feed_session_id=feed_session_id,
                            it=item_by_vid[s.autoparsed_vacancy_id],
                            result=err,
                            items=items,
                            finalized_vids=finalized_vids,
                            bot=bot,
                            silent_feed=silent_feed,
                            send_error_screenshot_to_user=send_error_screenshot_to_user,
                            autorespond_progress=autorespond_progress,
                            resume_blob=resume_blob,
                        )

            # ``apply_to_vacancies_ui_batch`` can return early with abort_reason set:
            # - negotiations_limit: stops after the vacancy that hit HH's response limit;
            #   later specs in this batch never get ``on_item_done``.
            # - cancelled: ``cancel_check`` returns True before remaining specs run.
            # In those cases we must still finalize every row in ``items`` so autorespond
            # progress ticks once per work unit (otherwise done < total forever).
            for it in items:
                vid = int(it["autoparsed_vacancy_id"])
                if vid not in finalized_vids:
                    if abort_reason == "negotiations_limit":
                        detail = "batch_abort:negotiations_limit"
                    elif abort_reason == "cancelled":
                        detail = "batch_abort:cancelled"
                    else:
                        detail = "batch_missing_result"
                    await _finalize_batch_item_async(
                        self=self,
                        session_factory=session_factory,
                        user_id=user_id,
                        chat_id=chat_id,
                        locale=locale,
                        hh_linked_account_id=hh_linked_account_id,
                        feed_session_id=feed_session_id,
                        it=it,
                        result=ApplyResult(
                            outcome=ApplyOutcome.ERROR,
                            detail=detail,
                        ),
                        items=items,
                        finalized_vids=finalized_vids,
                        bot=bot,
                        silent_feed=silent_feed,
                        send_error_screenshot_to_user=send_error_screenshot_to_user,
                        autorespond_progress=autorespond_progress,
                        resume_blob=resume_blob,
                    )

            if abort_reason == "negotiations_limit":
                await _notify_negotiations_limit_exceeded(
                    bot, int(chat_id), locale, autorespond_progress
                )
            elif abort_reason == "cancelled":
                from src.services.autorespond_progress import clear_hh_ui_batch_checkpoint_sync

                tk = autorespond_progress.get("task_key") if autorespond_progress else None
                if tk:
                    clear_hh_ui_batch_checkpoint_sync(int(chat_id), str(tk))

        processed = len(items)
        if abort_reason == "negotiations_limit":
            return {"status": "ok", "processed": processed, "abort": "negotiations_limit"}
        if abort_reason == "cancelled":
            return {"status": "cancelled", "processed": processed, "abort": "cancelled"}
        return {"status": "ok", "processed": processed}
    finally:
        with contextlib.suppress(Exception):
            await bot.session.close()


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="hh_ui.apply_to_vacancies_batch",
    queue="hh_ui",
    soft_time_limit=settings.hh_ui_apply_batch_task_soft_time_limit,
    time_limit=settings.hh_ui_apply_batch_task_time_limit,
)
def apply_to_vacancies_batch_ui_task(
    self,
    user_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
    hh_linked_account_id: int,
    feed_session_id: int,
    items: list[dict],
    cover_letter_style: str,
    cover_task_enabled: bool,
    silent_feed: bool = True,
    autorespond_progress: dict | None = None,
) -> dict:
    from celery.exceptions import SoftTimeLimitExceeded

    from src.services.autorespond_progress import (
        clear_hh_ui_batch_active_sync,
        load_hh_ui_batch_checkpoint_full_sync,
        set_hh_ui_batch_active_sync,
    )

    tk = autorespond_progress.get("task_key") if autorespond_progress else None
    cid = str(getattr(self.request, "id", None) or "")
    if tk and cid:
        set_hh_ui_batch_active_sync(int(chat_id), str(tk), cid)
    try:
        result = run_async(
            lambda sf: _apply_batch_ui_async(
                self,
                sf,
                user_id,
                chat_id,
                message_id,
                locale,
                hh_linked_account_id,
                feed_session_id,
                items,
                cover_letter_style,
                cover_task_enabled,
                silent_feed=silent_feed,
                autorespond_progress=autorespond_progress,
            )
        )
        _maybe_enqueue_next_ui_batch_from_tail(
            user_id=user_id,
            chat_id=chat_id,
            message_id=message_id,
            locale=locale,
            hh_linked_account_id=hh_linked_account_id,
            feed_session_id=feed_session_id,
            cover_letter_style=cover_letter_style,
            cover_task_enabled=cover_task_enabled,
            silent_feed=silent_feed,
            autorespond_progress=autorespond_progress,
            batch_result=result,
        )
        return result
    except SoftTimeLimitExceeded:
        if tk:
            full = load_hh_ui_batch_checkpoint_full_sync(int(chat_id), str(tk))
            if full:
                remaining, resume = full
                if remaining:
                    logger.warning(
                        "hh_ui_apply_batch_soft_timeout_resume",
                        user_id=user_id,
                        chat_id=chat_id,
                        task_key=tk,
                        remaining_count=len(remaining),
                    )
                    if resume:
                        apply_to_vacancies_batch_ui_task.delay(
                            **{**resume, "items": remaining}
                        )
                    else:
                        apply_to_vacancies_batch_ui_task.delay(
                            user_id=user_id,
                            chat_id=chat_id,
                            message_id=message_id,
                            locale=locale,
                            hh_linked_account_id=hh_linked_account_id,
                            feed_session_id=feed_session_id,
                            items=remaining,
                            cover_letter_style=cover_letter_style,
                            cover_task_enabled=cover_task_enabled,
                            silent_feed=silent_feed,
                            autorespond_progress=autorespond_progress,
                        )
        else:
            logger.warning(
                "hh_ui_apply_batch_soft_timeout",
                user_id=user_id,
                chat_id=chat_id,
                has_task_key=False,
            )
        raise
    finally:
        if tk:
            clear_hh_ui_batch_active_sync(int(chat_id), str(tk))


def _maybe_enqueue_next_ui_batch_from_tail(
    *,
    user_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
    hh_linked_account_id: int,
    feed_session_id: int,
    cover_letter_style: str,
    cover_task_enabled: bool,
    silent_feed: bool,
    autorespond_progress: dict | None,
    batch_result: dict,
) -> None:
    """When ``run_autorespond`` stopped but Redis still holds parent tail rows, enqueue the next batch.

    The parent normally calls ``.delay()`` for every chunk while its loop runs. If the parent
    task exited (crash, timeout, worker restart) before dispatching the rest, only the first
    ``hh_ui`` task(s) exist; this picks up the remaining rows from ``save_autorespond_ui_tail_sync``.
    """
    if not autorespond_progress or not autorespond_progress.get("task_key"):
        return
    if not isinstance(batch_result, dict) or batch_result.get("status") != "ok":
        return
    if batch_result.get("abort"):
        return
    task_key = str(autorespond_progress["task_key"])
    from src.core.celery_async import normalize_celery_task_id
    from src.services.autorespond_progress import (
        clear_autorespond_parent_loop_active_sync,
        hh_ui_batch_resume_payload,
        is_autorespond_parent_loop_active_sync,
        pop_autorespond_ui_tail_batch_sync,
    )
    from src.services.celery_active import celery_task_id_is_active

    parent_celery_id = normalize_celery_task_id(autorespond_progress.get("celery_task_id"))
    # Parent loop flag is cleared in ``run_autorespond`` ``finally`` when dispatch finished.
    # Only while that flag is set may the parent still be enqueueing more ``.delay()`` calls.
    # Do NOT call ``celery_task_id_is_active`` when the flag is clear: ``inspect().active()``
    # can falsely keep the parent id (timing / broker) and block tail recovery forever.
    if is_autorespond_parent_loop_active_sync(int(chat_id), task_key):
        if parent_celery_id and celery_task_id_is_active(parent_celery_id):
            logger.info(
                "hh_ui_apply_batch_tail_chain_skip_parent_dispatching",
                chat_id=chat_id,
                task_key=task_key,
                parent_celery_id=parent_celery_id,
            )
            return
        # Stale loop flag (e.g. parent process killed without ``finally``).
        clear_autorespond_parent_loop_active_sync(int(chat_id), task_key)
    batch = pop_autorespond_ui_tail_batch_sync(
        int(chat_id), task_key, settings.hh_ui_apply_batch_size
    )
    if not batch:
        logger.info(
            "hh_ui_apply_batch_tail_chain_no_pending_rows",
            chat_id=chat_id,
            task_key=task_key,
        )
        return
    resume = hh_ui_batch_resume_payload(
        user_id=user_id,
        chat_id=chat_id,
        message_id=message_id,
        locale=locale,
        hh_linked_account_id=hh_linked_account_id,
        feed_session_id=feed_session_id,
        cover_letter_style=cover_letter_style,
        cover_task_enabled=cover_task_enabled,
        silent_feed=silent_feed,
        autorespond_progress=autorespond_progress,
    )
    logger.info(
        "hh_ui_apply_batch_tail_chain",
        user_id=user_id,
        chat_id=chat_id,
        task_key=task_key,
        next_batch=len(batch),
    )
    apply_to_vacancies_batch_ui_task.delay(**{**resume, "items": batch})


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
    result: ApplyResult | None = None
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
                played, abort_reason_single = await asyncio.to_thread(
                    apply_to_vacancies_ui_batch,
                    storage_state=storage,
                    items=[
                        VacancyApplySpec(
                            autoparsed_vacancy_id=autoparsed_vacancy_id,
                            hh_vacancy_id=hh_vacancy_id,
                            vacancy_url=url,
                            resume_hh_id=resume_id,
                            cover_letter=cover_letter or "",
                        )
                    ],
                    config=config,
                    log_user_id=user_id,
                    max_retries=settings.hh_ui_apply_max_retries,
                    retry_initial_seconds=settings.hh_ui_apply_retry_initial_seconds,
                    retry_delay_cap_seconds=settings.hh_ui_apply_retry_delay_cap_seconds,
                )
                result = played[0][1]
                if abort_reason_single == "negotiations_limit":
                    await _notify_negotiations_limit_exceeded(
                        bot, int(chat_id), locale, autorespond_progress
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

        status, err_code = await _persist_ui_apply_attempt_and_feed_effects(
            session_factory=session_factory,
            user_id=user_id,
            hh_linked_account_id=hh_linked_account_id,
            autoparsed_vacancy_id=autoparsed_vacancy_id,
            hh_vacancy_id=hh_vacancy_id,
            resume_id=resume_id,
            feed_session_id=feed_session_id,
            result=result,
            silent_feed=silent_feed,
        )
        logger.info(
            "hh_ui_apply_attempt_recorded",
            task_id=getattr(self.request, "id", None),
            user_id=user_id,
            vacancy_id=autoparsed_vacancy_id,
            status=status,
        )

        if result.outcome == ApplyOutcome.VACANCY_UNAVAILABLE:
            async with session_factory() as s_reload:
                fr = VacancyFeedSessionRepository(s_reload)
                feed_session = await fr.get_by_id(feed_session_id)
        elif status != "success" and status != "needs_employer_questions":
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
                and result.outcome != ApplyOutcome.SESSION_EXPIRED
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
            and result.outcome != ApplyOutcome.SESSION_EXPIRED
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
                from src.services.autorespond_progress import (
                    increment_autorespond_failed_sync,
                    tick_autorespond_bar,
                )

                if result is not None and _ui_outcome_increments_autorespond_failed(result.outcome):
                    increment_autorespond_failed_sync(
                        int(chat_id),
                        str(autorespond_progress["task_key"]),
                        1,
                    )
                await tick_autorespond_bar(
                    bot=bot,
                    chat_id=chat_id,
                    task_key=str(autorespond_progress["task_key"]),
                    total=int(autorespond_progress["total"]),
                    locale=str(autorespond_progress.get("locale") or locale),
                    footer_failed_line=None,
                    title=autorespond_progress.get("title"),
                    celery_task_id=autorespond_progress.get("celery_task_id"),
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
