"""Celery tasks: HH.ru UI apply (Playwright) + autorespond apply pump.

Two roles
---------
* :func:`apply_to_vacancy_ui_task` — single-vacancy apply triggered by the user's
  feed (one click, immediate apply). One Chromium session per task.

* :func:`apply_pump_task` — long-lived consumer for the autorespond pipeline.
  Pops batches from the Redis ready ZSET, reads pre-generated cover letters,
  runs a Playwright batch, ticks the progress bar per item, chains itself when
  the soft time limit approaches. No tail-chain / parent-heartbeat coordination.

Old ``apply_to_vacancies_batch_ui_task`` is retained as a deprecation shim that
re-routes in-flight broker messages to the new pump.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
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
from src.core.system_load import get_system_load_guard
from src.repositories.app_settings import AppSettingRepository
from src.repositories.hh_application_attempt import HhApplicationAttemptRepository
from src.repositories.hh_linked_account import HhLinkedAccountRepository
from src.services.autorespond_pipeline_state import (
    fetch_pregen_letter,
    is_pregen_pending_for_vacancy,
    mark_pregen_pending,
    pop_ready_batch,
    pregen_pending_count,
    ready_remaining_count,
    release_pump_lock,
    renew_pump_lock,
    touch_pump_heartbeat,
    try_acquire_pump_lock,
)
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

    Terminal without retry: SUCCESS, ALREADY_RESPONDED, EMPLOYER_QUESTIONS,
    VACANCY_UNAVAILABLE. Retryable: ERROR, RATE_LIMITED, NO_APPLY_BUTTON,
    SESSION_EXPIRED. CAPTCHA terminal (no automated retry).
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
    """Redis footer: count everything except clear success / already applied / preflight skip."""
    return outcome not in (
        ApplyOutcome.SUCCESS,
        ApplyOutcome.ALREADY_RESPONDED,
        ApplyOutcome.VACANCY_UNAVAILABLE,
        ApplyOutcome.EMPLOYER_QUESTIONS,
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
        vac_repo = AutoparsedVacancyRepository(session)
        if await vac_repo.get_by_id(autoparsed_vacancy_id) is None:
            return status, err_code
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
    finish_progress_task = bool(autorespond_progress.get("finish_progress_task", True))
    from src.services.autorespond_pipeline_state import clear_all_pipeline_state
    from src.services.autorespond_progress import (
        clear_autorespond_done_counter,
        clear_autorespond_failed_counter,
        set_autorespond_cancelled,
    )
    from src.services.progress_service import ProgressService, create_progress_redis

    await set_autorespond_cancelled(chat_id, task_key)
    clear_all_pipeline_state(chat_id, task_key)
    if not finish_progress_task:
        redis = create_progress_redis()
        try:
            svc = ProgressService(bot, chat_id, redis, locale)
            await svc.update_footer(
                task_key,
                [get_text("hh-ui-negotiations-limit-shortage", locale)],
            )
        finally:
            await redis.aclose()
        return
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


# ---------------------------------------------------------------------------
# Apply pump (autorespond pipeline consumer)
# ---------------------------------------------------------------------------


def _autorespond_progress_from_envelope(resume_envelope: dict[str, Any]) -> dict[str, Any] | None:
    ap = resume_envelope.get("autorespond_progress")
    return ap if isinstance(ap, dict) else None


async def _resolve_cover_letter_for_apply(
    session_factory: async_sessionmaker[AsyncSession],
    chat_id: int,
    task_key: str,
    autoparsed_vacancy_id: int,
) -> str:
    """Load cover letter from Redis cache or DB; autorespond applies require non-empty text."""
    letter = fetch_pregen_letter(chat_id, task_key, autoparsed_vacancy_id)
    if letter and letter.strip():
        return letter.strip()
    from src.repositories.autoparse import AutoparsedVacancyRepository

    async with session_factory() as session:
        repo = AutoparsedVacancyRepository(session)
        vacancy = await repo.get_by_id(autoparsed_vacancy_id)
        db_letter = getattr(vacancy, "autorespond_cover_letter", None) if vacancy else None
        if db_letter and db_letter.strip():
            return db_letter.strip()
    return ""


def _schedule_pregen_for_apply_spec(
    *,
    chat_id: int,
    task_key: str,
    user_id: int,
    apply_spec: dict[str, Any],
    resume_envelope: dict[str, Any],
) -> None:
    """Re-enqueue cover letter generation; apply follows after ``enqueue_autorespond_apply_unit``."""
    if not resume_envelope.get("cover_task_enabled", True):
        return
    vid = int(apply_spec["autoparsed_vacancy_id"])
    mark_pregen_pending(int(chat_id), task_key, [vid])
    from src.worker.tasks.cover_letter import pregenerate_for_apply_task

    pregenerate_for_apply_task.delay(
        task_key=task_key,
        chat_id=int(chat_id),
        user_id=int(user_id),
        autoparsed_vacancy_id=vid,
        resume_id=str(apply_spec["resume_id"]),
        cover_letter_style=str(resume_envelope.get("cover_letter_style") or "professional"),
        apply_spec=apply_spec,
    )


async def _defer_apply_unit_missing_cover_letter(
    *,
    chat_id: int,
    task_key: str,
    user_id: int,
    apply_spec: dict[str, Any],
    resume_envelope: dict[str, Any],
) -> None:
    """Letter not ready yet: wait for in-flight pregen or schedule a new one (no bar tick)."""
    vid = int(apply_spec["autoparsed_vacancy_id"])
    if is_pregen_pending_for_vacancy(int(chat_id), task_key, vid):
        logger.info(
            "apply_pump_missing_cover_letter_waiting_pregen",
            chat_id=chat_id,
            task_key=task_key,
            vacancy_id=vid,
        )
        await asyncio.sleep(0.5)
        return
    logger.warning(
        "apply_pump_missing_cover_letter_reschedule_pregen",
        chat_id=chat_id,
        task_key=task_key,
        vacancy_id=vid,
    )
    _schedule_pregen_for_apply_spec(
        chat_id=int(chat_id),
        task_key=task_key,
        user_id=user_id,
        apply_spec=apply_spec,
        resume_envelope=resume_envelope,
    )
    await asyncio.sleep(0.5)


async def _finalize_pump_item_async(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    chat_id: int,
    user_id: int,
    locale: str,
    hh_linked_account_id: int,
    spec: dict[str, Any],
    result: ApplyResult,
    autorespond_progress: dict[str, Any] | None,
    bot: Any,
    silent_feed: bool,
    send_error_screenshot_to_user: bool,
) -> None:
    """Persist attempt + tick progress bar for one pump item."""
    from src.services.autorespond_progress import (
        increment_autorespond_employer_test_sync,
        increment_autorespond_failed_sync,
        is_autorespond_cancelled_sync,
        tick_autorespond_bar,
    )
    from src.services.progress_cancel import is_user_cancelled_sync

    task_key: str | None = None
    if autorespond_progress and autorespond_progress.get("task_key"):
        task_key = str(autorespond_progress["task_key"])
    if task_key and (
        is_autorespond_cancelled_sync(int(chat_id), task_key)
        or is_user_cancelled_sync(int(chat_id), task_key)
    ):
        return

    vid = int(spec["autoparsed_vacancy_id"])
    hh_id = str(spec["hh_vacancy_id"])
    resume_id = str(spec["resume_id"])

    if not (result.detail or "").startswith("batch_abort:"):
        await _persist_ui_apply_attempt_and_feed_effects(
            session_factory=session_factory,
            user_id=user_id,
            hh_linked_account_id=hh_linked_account_id,
            autoparsed_vacancy_id=vid,
            hh_vacancy_id=hh_id,
            resume_id=resume_id,
            feed_session_id=0,
            result=result,
            silent_feed=silent_feed,
        )

    if autorespond_progress and task_key:
        try:
            if _ui_outcome_increments_autorespond_failed(result.outcome):
                increment_autorespond_failed_sync(int(chat_id), task_key, 1)
            if result.outcome == ApplyOutcome.EMPLOYER_QUESTIONS:
                increment_autorespond_employer_test_sync(int(chat_id), task_key, 1)
            await tick_autorespond_bar(
                bot=bot,
                chat_id=int(chat_id),
                task_key=task_key,
                total=int(autorespond_progress["total"]),
                locale=str(autorespond_progress.get("locale") or locale),
                footer_failed_line=None,
                title=autorespond_progress.get("title"),
                celery_task_id=autorespond_progress.get("celery_task_id"),
                bar_index=int(autorespond_progress.get("bar_index", 0)),
                finish_progress_task=bool(
                    autorespond_progress.get("finish_progress_task", True)
                ),
                streaming_autorespond=bool(
                    autorespond_progress.get("streaming_autorespond")
                ),
            )
        except Exception as exc:
            logger.warning(
                "apply_pump_tick_failed",
                vacancy_id=vid,
                task_key=task_key,
                error=str(exc)[:300],
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
                int(chat_id),
                BufferedInputFile(result.screenshot_bytes, err_name),
            )


def _pump_shift_should_continue(
    *,
    shift_started: float,
    soft_time_limit: float,
    grace_seconds: float,
) -> bool:
    elapsed = time.monotonic() - shift_started
    return elapsed + grace_seconds < soft_time_limit


async def _apply_pump_async(
    self,
    session_factory: async_sessionmaker[AsyncSession],
    task_key: str,
    chat_id: int,
    resume_envelope: dict[str, Any],
) -> dict:
    """Long-lived consumer of the autorespond ready ZSET; chains self before soft-timeout."""
    from src.services.autorespond_progress import (
        ensure_autorespond_progress_task_state_if_missing,
        is_autorespond_cancelled_sync,
    )
    from src.services.progress_cancel import is_user_cancelled_sync

    pump_owner = str(getattr(getattr(self, "request", None), "id", None) or "unknown")

    def _pump_cancelled() -> bool:
        return is_autorespond_cancelled_sync(int(chat_id), task_key) or is_user_cancelled_sync(
            int(chat_id), task_key
        )

    if _pump_cancelled():
        return {"status": "skipped", "processed": 0, "abort": "cancelled"}

    if not try_acquire_pump_lock(int(chat_id), task_key, pump_owner):
        logger.info(
            "apply_pump_skipped_lock_held",
            chat_id=chat_id,
            task_key=task_key,
            owner=pump_owner,
        )
        return {"status": "skipped", "processed": 0, "abort": "pump_lock_held"}

    bot = self.create_bot()
    autorespond_progress = _autorespond_progress_from_envelope(resume_envelope)
    locale = str(resume_envelope.get("locale") or "ru")
    user_id = int(resume_envelope.get("user_id") or 0)
    hh_linked_account_id = int(resume_envelope.get("hh_linked_account_id") or 0)
    silent_feed = bool(resume_envelope.get("silent_feed", True))

    if user_id <= 0 or hh_linked_account_id <= 0:
        with contextlib.suppress(Exception):
            await bot.session.close()
        return {"status": "error", "reason": "bad_envelope"}

    shift_started = time.monotonic()
    soft_limit = float(settings.autorespond_apply_pump_soft_time_limit)
    grace = float(settings.autorespond_apply_pump_chain_grace_seconds)
    batch_size = int(settings.hh_ui_apply_batch_size)
    guard = get_system_load_guard()

    cipher = HhTokenCipher(settings.hh_token_encryption_key)
    processed = 0
    abort_reason: str | None = None

    if autorespond_progress:
        with contextlib.suppress(Exception):
            await ensure_autorespond_progress_task_state_if_missing(
                bot=bot,
                chat_id=int(chat_id),
                autorespond_progress=autorespond_progress,
                locale=locale,
            )

    try:
        # Load account + decrypted browser session once per shift (saves Postgres + Fernet work).
        async with session_factory() as session:
            acc = await HhLinkedAccountRepository(session).get_by_id(hh_linked_account_id)
            if not acc or not acc.browser_storage_enc:
                logger.warning(
                    "apply_pump_missing_browser_session",
                    chat_id=chat_id,
                    task_key=task_key,
                    account_id=hh_linked_account_id,
                )
                return {"status": "error", "reason": "no_browser_session"}
            storage = decrypt_browser_storage(acc.browser_storage_enc, cipher)
            if not storage:
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

        touch_pump_heartbeat(int(chat_id), task_key)

        while _pump_shift_should_continue(
            shift_started=shift_started,
            soft_time_limit=soft_limit,
            grace_seconds=grace,
        ):
            if _pump_cancelled():
                abort_reason = "cancelled"
                break
            await guard.wait_if_overloaded("apply_pump_between_batches")
            touch_pump_heartbeat(int(chat_id), task_key)
            renew_pump_lock(int(chat_id), task_key, pump_owner)

            batch_specs = pop_ready_batch(int(chat_id), task_key, batch_size)
            if not batch_specs:
                if pregen_pending_count(int(chat_id), task_key) > 0 and ready_remaining_count(
                    int(chat_id), task_key
                ) > 0:
                    # Ready set is non-empty but ZPOPMIN race: sleep briefly and retry.
                    await asyncio.sleep(0.5)
                    continue
                if pregen_pending_count(int(chat_id), task_key) > 0:
                    # Dispatcher seeded specs but pregen tasks not done; wait a tick.
                    await asyncio.sleep(0.5)
                    continue
                break

            # Resolve cover letters (apply units enter the queue only after pregen saved one).
            specs: list[VacancyApplySpec] = []
            for spec in batch_specs:
                letter = await _resolve_cover_letter_for_apply(
                    session_factory,
                    int(chat_id),
                    task_key,
                    int(spec["autoparsed_vacancy_id"]),
                )
                if not letter:
                    await _defer_apply_unit_missing_cover_letter(
                        chat_id=int(chat_id),
                        task_key=task_key,
                        user_id=user_id,
                        apply_spec=spec,
                        resume_envelope=resume_envelope,
                    )
                    continue
                specs.append(
                    VacancyApplySpec(
                        autoparsed_vacancy_id=int(spec["autoparsed_vacancy_id"]),
                        hh_vacancy_id=str(spec["hh_vacancy_id"]),
                        vacancy_url=normalize_hh_vacancy_url(
                            str(spec.get("vacancy_url") or ""),
                            str(spec["hh_vacancy_id"]),
                        ),
                        resume_hh_id=str(spec["resume_id"]),
                        cover_letter=letter,
                    )
                )
            if not specs:
                continue

            loop = asyncio.get_running_loop()
            done_vids: set[int] = set()

            def _on_item_done(
                spec: VacancyApplySpec,
                result: ApplyResult,
                _done_vids: set[int] = done_vids,
                _loop=loop,
            ) -> None:
                # Playwright runs in a thread; bounce finalization back to the main loop.
                _done_vids.add(spec.autoparsed_vacancy_id)
                fut = asyncio.run_coroutine_threadsafe(
                    _finalize_pump_item_async(
                        session_factory=session_factory,
                        chat_id=chat_id,
                        user_id=user_id,
                        locale=locale,
                        hh_linked_account_id=hh_linked_account_id,
                        spec={
                            "autoparsed_vacancy_id": spec.autoparsed_vacancy_id,
                            "hh_vacancy_id": spec.hh_vacancy_id,
                            "resume_id": spec.resume_hh_id,
                        },
                        result=result,
                        autorespond_progress=autorespond_progress,
                        bot=bot,
                        silent_feed=silent_feed,
                        send_error_screenshot_to_user=send_error_screenshot_to_user,
                    ),
                    _loop,
                )
                fut.result(timeout=300)

            def _cancel_check_sync() -> bool:
                return is_autorespond_cancelled_sync(int(chat_id), task_key) or is_user_cancelled_sync(
                    int(chat_id), task_key
                )

            def _run_batch(_specs=specs):
                return apply_to_vacancies_ui_batch(
                    storage_state=storage,
                    items=_specs,
                    config=config,
                    log_user_id=user_id,
                    max_retries=settings.hh_ui_apply_max_retries,
                    retry_initial_seconds=settings.hh_ui_apply_retry_initial_seconds,
                    retry_delay_cap_seconds=settings.hh_ui_apply_retry_delay_cap_seconds,
                    on_item_done=_on_item_done,
                    cancel_check=_cancel_check_sync,
                )

            try:
                _, batch_abort = await asyncio.to_thread(_run_batch)
            except Exception as exc:
                logger.exception("apply_pump_batch_failed", error=str(exc))
                # Finalize every spec in this batch that didn't get an on_item_done callback.
                err = ApplyResult(outcome=ApplyOutcome.ERROR, detail=str(exc)[:500])
                for s in specs:
                    if s.autoparsed_vacancy_id in done_vids:
                        continue
                    await _finalize_pump_item_async(
                        session_factory=session_factory,
                        chat_id=chat_id,
                        user_id=user_id,
                        locale=locale,
                        hh_linked_account_id=hh_linked_account_id,
                        spec={
                            "autoparsed_vacancy_id": s.autoparsed_vacancy_id,
                            "hh_vacancy_id": s.hh_vacancy_id,
                            "resume_id": s.resume_hh_id,
                        },
                        result=err,
                        autorespond_progress=autorespond_progress,
                        bot=bot,
                        silent_feed=silent_feed,
                        send_error_screenshot_to_user=send_error_screenshot_to_user,
                    )
                processed += len(specs)
                continue

            # Apply_to_vacancies_ui_batch may abort early (negotiations_limit / cancelled).
            for s in specs:
                if s.autoparsed_vacancy_id in done_vids:
                    continue
                if batch_abort == "negotiations_limit":
                    detail = "batch_abort:negotiations_limit"
                elif batch_abort == "cancelled":
                    detail = "batch_abort:cancelled"
                else:
                    detail = "batch_missing_result"
                await _finalize_pump_item_async(
                    session_factory=session_factory,
                    chat_id=chat_id,
                    user_id=user_id,
                    locale=locale,
                    hh_linked_account_id=hh_linked_account_id,
                    spec={
                        "autoparsed_vacancy_id": s.autoparsed_vacancy_id,
                        "hh_vacancy_id": s.hh_vacancy_id,
                        "resume_id": s.resume_hh_id,
                    },
                    result=ApplyResult(outcome=ApplyOutcome.ERROR, detail=detail),
                    autorespond_progress=autorespond_progress,
                    bot=bot,
                    silent_feed=silent_feed,
                    send_error_screenshot_to_user=send_error_screenshot_to_user,
                )

            processed += len(specs)

            if batch_abort == "negotiations_limit":
                await _notify_negotiations_limit_exceeded(
                    bot, int(chat_id), locale, autorespond_progress
                )
                abort_reason = "negotiations_limit"
                break
            if batch_abort == "cancelled":
                abort_reason = "cancelled"
                break

        # End of shift: decide whether to chain.
        release_pump_lock(int(chat_id), task_key, pump_owner)
        if (
            abort_reason is None
            and not _pump_cancelled()
            and ready_remaining_count(int(chat_id), task_key) > 0
        ):
            logger.info(
                "apply_pump_chaining_self",
                chat_id=chat_id,
                task_key=task_key,
                processed=processed,
                elapsed=round(time.monotonic() - shift_started, 1),
                remaining=ready_remaining_count(int(chat_id), task_key),
            )
            apply_pump_task.delay(
                task_key=task_key,
                chat_id=int(chat_id),
                resume_envelope=resume_envelope,
            )
        elif (
            abort_reason is None
            and not _pump_cancelled()
            and autorespond_progress
            and autorespond_progress.get("streaming_autorespond")
        ):
            from src.services.autorespond_progress import (
                maybe_finish_streaming_autorespond_progress,
            )

            await maybe_finish_streaming_autorespond_progress(
                bot=bot,
                chat_id=int(chat_id),
                task_key=task_key,
                locale=str(autorespond_progress.get("locale") or locale),
                bar_index=int(autorespond_progress.get("bar_index", 0)),
            )

        return {
            "status": "ok",
            "processed": processed,
            "abort": abort_reason,
        }
    finally:
        release_pump_lock(int(chat_id), task_key, pump_owner)
        with contextlib.suppress(Exception):
            await bot.session.close()


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="autorespond.apply_pump",
    queue="hh_ui",
    soft_time_limit=settings.autorespond_apply_pump_soft_time_limit,
    time_limit=settings.autorespond_apply_pump_time_limit,
    acks_late=True,
)
def apply_pump_task(
    self,
    task_key: str,
    chat_id: int,
    resume_envelope: dict[str, Any],
) -> dict:
    from celery.exceptions import SoftTimeLimitExceeded

    try:
        return run_async(
            lambda sf: _apply_pump_async(self, sf, task_key, int(chat_id), resume_envelope)
        )
    except SoftTimeLimitExceeded:
        from src.services.autorespond_progress import is_autorespond_cancelled_sync
        from src.services.progress_cancel import is_user_cancelled_sync

        # Chain ourselves so the bar still converges; recover_stalled is the fallback.
        logger.warning(
            "apply_pump_soft_time_limit_chain",
            chat_id=chat_id,
            task_key=task_key,
        )
        if (
            ready_remaining_count(int(chat_id), task_key) > 0
            and not is_autorespond_cancelled_sync(int(chat_id), task_key)
            and not is_user_cancelled_sync(int(chat_id), task_key)
        ):
            apply_pump_task.delay(
                task_key=task_key,
                chat_id=int(chat_id),
                resume_envelope=resume_envelope,
            )
        raise


# ---------------------------------------------------------------------------
# Deprecation shim for in-flight ``apply_to_vacancies_batch_ui_task`` messages
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="hh_ui.apply_to_vacancies_batch",
    queue="hh_ui",
    soft_time_limit=120,
    time_limit=150,
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
    """Deprecated: routes any in-flight broker messages to ``apply_pump_task`` instead.

    The old parent loop fan-out is gone. Items are re-seeded into the ready ZSET so
    the pump can finalize the run; the bar still ticks per item.
    """
    from src.services.autorespond_pipeline_state import (
        save_pipeline_envelope,
        seed_ready_to_apply,
    )

    logger.warning(
        "apply_to_vacancies_batch_ui_task_deprecated",
        chat_id=chat_id,
        items=len(items),
        task_key=(autorespond_progress or {}).get("task_key"),
    )
    if not autorespond_progress or not autorespond_progress.get("task_key"):
        return {"status": "skipped", "reason": "no_task_key"}
    task_key = str(autorespond_progress["task_key"])
    specs = [
        {
            "autoparsed_vacancy_id": int(it["autoparsed_vacancy_id"]),
            "hh_vacancy_id": str(it["hh_vacancy_id"]),
            "resume_id": str(it["resume_id"]),
            "vacancy_url": normalize_hh_vacancy_url(
                str(it.get("vacancy_url") or ""), str(it["hh_vacancy_id"])
            ),
        }
        for it in items
        if isinstance(it, dict)
    ]
    if specs:
        seed_ready_to_apply(int(chat_id), task_key, specs)
        save_pipeline_envelope(
            int(chat_id),
            task_key,
            {
                "resume_envelope": {
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "locale": locale,
                    "hh_linked_account_id": hh_linked_account_id,
                    "feed_session_id": feed_session_id,
                    "cover_letter_style": cover_letter_style,
                    "cover_task_enabled": cover_task_enabled,
                    "silent_feed": silent_feed,
                    "autorespond_progress": autorespond_progress,
                },
                "total_work_units": int(autorespond_progress.get("total") or 0),
            },
        )
        apply_pump_task.delay(
            task_key=task_key,
            chat_id=int(chat_id),
            resume_envelope={
                "user_id": user_id,
                "chat_id": chat_id,
                "message_id": message_id,
                "locale": locale,
                "hh_linked_account_id": hh_linked_account_id,
                "feed_session_id": feed_session_id,
                "cover_letter_style": cover_letter_style,
                "cover_task_enabled": cover_task_enabled,
                "silent_feed": silent_feed,
                "autorespond_progress": autorespond_progress,
            },
        )
    return {"status": "rerouted", "items": len(specs)}


# ---------------------------------------------------------------------------
# Single-vacancy UI apply (feed-driven; unchanged contract)
# ---------------------------------------------------------------------------


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

        from src.services.hh.vacancy_public import hh_vacancy_public_preflight

        preflight = await hh_vacancy_public_preflight(hh_vacancy_id)
        if preflight.unavailable:
            result = ApplyResult(
                outcome=ApplyOutcome.VACANCY_UNAVAILABLE,
                detail="preflight_api",
            )
        elif preflight.requires_employer_test:
            result = ApplyResult(
                outcome=ApplyOutcome.EMPLOYER_QUESTIONS,
                detail="preflight_api:test_required",
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

        if result.outcome == ApplyOutcome.VACANCY_UNAVAILABLE or (
            status != "success" and status != "needs_employer_questions"
        ):
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
                    increment_autorespond_employer_test_sync,
                    increment_autorespond_failed_sync,
                    tick_autorespond_bar,
                )

                if result is not None and _ui_outcome_increments_autorespond_failed(result.outcome):
                    increment_autorespond_failed_sync(
                        int(chat_id),
                        str(autorespond_progress["task_key"]),
                        1,
                    )
                if result is not None and result.outcome == ApplyOutcome.EMPLOYER_QUESTIONS:
                    increment_autorespond_employer_test_sync(
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
                    bar_index=int(autorespond_progress.get("bar_index", 0)),
                    finish_progress_task=bool(
                        autorespond_progress.get("finish_progress_task", True)
                    ),
                )
        with contextlib.suppress(Exception):
            await bot.session.close()


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="hh_ui.apply_to_vacancy",
    queue="hh_ui",
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


@celery_app.task(name="hh_ui.periodic_resume_checkpoints")
def periodic_resume_hh_ui_checkpoints() -> int:
    """Safety net: re-enqueue HH UI batches from Redis checkpoints (legacy)."""
    import asyncio

    from src.services.task_restart import resume_hh_ui_batches_from_checkpoints

    return asyncio.run(resume_hh_ui_batches_from_checkpoints())
