"""Autorespond + UI apply: shared progress bar until each Playwright/API step completes."""

from __future__ import annotations

import json
from typing import Any

import redis as sync_redis
from redis.exceptions import RedisError, WatchError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import settings
from src.core.celery_async import normalize_celery_task_id
from src.core.i18n import get_text
from src.core.logging import get_logger
from src.services.progress_service import ProgressService, create_progress_redis

logger = get_logger(__name__)

_DONE_TTL_S = 4 * 3600


def autorespond_done_redis_key(chat_id: int, task_key: str) -> str:
    return f"progress:autorespond_done:{chat_id}:{task_key}"


def autorespond_cancel_redis_key(chat_id: int, task_key: str) -> str:
    return f"progress:autorespond_cancel:{chat_id}:{task_key}"


def autorespond_failed_redis_key(chat_id: int, task_key: str) -> str:
    """UI apply outcomes that are not success / already / preflight-unavailable (see hh_ui_apply)."""
    return f"progress:autorespond_failed:{chat_id}:{task_key}"


def hh_ui_batch_checkpoint_key(chat_id: int, task_key: str) -> str:
    """Remaining ``items`` for ``hh_ui.apply_to_vacancies_batch`` resume after soft timeout."""
    return f"checkpoint:hh_ui_apply_batch:{chat_id}:{task_key}"


def hh_ui_resume_envelope_key(chat_id: int, task_key: str) -> str:
    """Durable kwargs for ``apply_to_vacancies_batch_ui_task`` (without ``items``), mirrored from checkpoint."""
    return f"autorespond:hh_ui_resume_envelope:{chat_id}:{task_key}"


def save_hh_ui_resume_envelope_sync(
    chat_id: int, task_key: str, resume: dict[str, Any]
) -> None:
    """Persist resume kwargs so refresh works if the checkpoint JSON loses the ``resume`` key."""
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        r.set(
            hh_ui_resume_envelope_key(chat_id, task_key),
            json.dumps(resume),
            ex=_DONE_TTL_S,
        )
    finally:
        r.close()


def load_hh_ui_resume_envelope_sync(
    chat_id: int, task_key: str,
) -> dict[str, Any] | None:
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        raw = r.get(hh_ui_resume_envelope_key(chat_id, task_key))
        if not raw:
            return None
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    finally:
        r.close()


def clear_hh_ui_resume_envelope_sync(chat_id: int, task_key: str) -> None:
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        r.delete(hh_ui_resume_envelope_key(chat_id, task_key))
    finally:
        r.close()


async def build_hh_ui_resume_envelope_fallback_async(
    session_factory: async_sessionmaker[AsyncSession],
    chat_id: int,
    task_key: str,
) -> dict[str, Any] | None:
    """Rebuild ``hh_ui_batch_resume_payload`` from DB + progress Redis when envelope is missing."""
    if not task_key.startswith("autorespond:"):
        return None
    parts = task_key.split(":", 2)
    if len(parts) != 3:
        return None
    try:
        company_id = int(parts[1])
    except ValueError:
        return None
    parent_celery_id = parts[2]

    from src.bot.modules.autoparse import services as ap_service
    from src.core.constants import AppSettingKey
    from src.repositories.app_settings import AppSettingRepository
    from src.repositories.autoparse import AutoparseCompanyRepository
    from src.repositories.user import UserRepository

    async with session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(chat_id)
        if not user:
            return None
        company_repo = AutoparseCompanyRepository(session)
        company = await company_repo.get_by_id(company_id)
        if not company or company.user_id != user.id or not company.autorespond_hh_linked_account_id:
            return None
        ap_settings = await ap_service.get_user_autoparse_settings(session, user.id)
        cover_letter_style = ap_settings.get("cover_letter_style", "professional")
        settings_repo = AppSettingRepository(session)
        cover_task_enabled = bool(
            await settings_repo.get_value(AppSettingKey.TASK_COVER_LETTER_ENABLED, default=True)
        )

    locale = user.language_code or "ru"
    title = company.vacancy_title or ""
    total = 1

    redis = create_progress_redis()
    try:
        raw = await redis.get(f"progress:task:{chat_id}:{task_key}")
        if raw:
            state = json.loads(raw)
            title = state.get("title") or title
            bars = state.get("bars") or []
            if bars and isinstance(bars[0], dict):
                t = bars[0].get("total")
                if isinstance(t, int) and t > 0:
                    total = t
    finally:
        await redis.aclose()

    autorespond_progress = {
        "task_key": task_key,
        "total": total,
        "locale": locale,
        "title": title,
        "celery_task_id": parent_celery_id,
    }
    return hh_ui_batch_resume_payload(
        user_id=user.id,
        chat_id=chat_id,
        message_id=0,
        locale=locale,
        hh_linked_account_id=int(company.autorespond_hh_linked_account_id),
        feed_session_id=0,
        cover_letter_style=str(cover_letter_style),
        cover_task_enabled=cover_task_enabled,
        silent_feed=True,
        autorespond_progress=autorespond_progress,
    )


def autorespond_ui_tail_key(chat_id: int, task_key: str) -> str:
    """Parent ``run_autorespond`` pending UI rows not yet dispatched (between child batches)."""
    return f"progress:autorespond_ui_tail:{chat_id}:{task_key}"


def autorespond_parent_loop_key(chat_id: int, task_key: str) -> str:
    """Set while ``run_autorespond`` is still iterating (dispatches multiple ``hh_ui`` batches)."""
    return f"progress:autorespond_parent_loop:{chat_id}:{task_key}"


def hh_ui_batch_resume_payload(
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
) -> dict[str, Any]:
    """JSON-serializable kwargs for ``apply_to_vacancies_batch_ui_task.delay`` (excluding ``items``)."""
    return {
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
    }


def hh_ui_batch_active_key(chat_id: int, task_key: str) -> str:
    """Child Celery task id for in-flight ``apply_to_vacancies_batch`` (parent may already be done)."""
    return f"hh_ui_batch_active:{chat_id}:{task_key}"


def set_hh_ui_batch_active_sync(chat_id: int, task_key: str, celery_task_id: str) -> None:
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        r.set(hh_ui_batch_active_key(chat_id, task_key), celery_task_id, ex=_DONE_TTL_S)
    finally:
        r.close()


def clear_hh_ui_batch_active_sync(chat_id: int, task_key: str) -> None:
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        r.delete(hh_ui_batch_active_key(chat_id, task_key))
    finally:
        r.close()


def get_hh_ui_batch_active_sync(chat_id: int, task_key: str) -> str | None:
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        v = r.get(hh_ui_batch_active_key(chat_id, task_key))
        return str(v) if v else None
    finally:
        r.close()


def save_hh_ui_batch_checkpoint_sync(
    chat_id: int,
    task_key: str,
    remaining_items: list[dict],
    *,
    resume: dict[str, Any] | None = None,
) -> None:
    """Persist remaining batch rows and kwargs for cold resume.

    Empty ``remaining_items`` still stores JSON with ``items: []`` when ``resume`` is set
    so progress refresh can merge with the parent tail between Playwright batches.
    Without ``resume``, an empty list deletes the key (nothing to resume).
    """
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    key = hh_ui_batch_checkpoint_key(chat_id, task_key)
    try:
        if not remaining_items and resume is None:
            r.delete(key)
            return
        payload: dict[str, Any] = {"items": remaining_items}
        if resume is not None:
            payload["resume"] = resume
            save_hh_ui_resume_envelope_sync(chat_id, task_key, resume)
        r.set(key, json.dumps(payload), ex=_DONE_TTL_S)
    finally:
        r.close()


def load_hh_ui_batch_checkpoint_full_sync(
    chat_id: int, task_key: str,
) -> tuple[list[dict], dict[str, Any] | None] | None:
    """Return (items, resume) when a checkpoint exists.

    ``items`` may be empty when the child batch finished but ``resume`` is kept for refresh.
    ``resume`` is None when the JSON has no ``resume`` key (legacy checkpoints).
    """
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    key = hh_ui_batch_checkpoint_key(chat_id, task_key)
    try:
        raw = r.get(key)
        if not raw:
            return None
        data = json.loads(raw)
        items = data.get("items")
        if not isinstance(items, list):
            return None
        clean_items = [x for x in items if isinstance(x, dict)]
        resume: dict[str, Any] | None
        if "resume" not in data:
            resume = None
        else:
            rsum = data.get("resume")
            resume = rsum if isinstance(rsum, dict) else None
        if not clean_items and not resume:
            return None
        return (clean_items, resume)
    finally:
        r.close()


def load_hh_ui_batch_checkpoint_sync(chat_id: int, task_key: str) -> list[dict] | None:
    """Return remaining items if a checkpoint exists (may be empty list when resume-only)."""
    full = load_hh_ui_batch_checkpoint_full_sync(chat_id, task_key)
    if not full:
        return None
    return full[0]


def save_autorespond_ui_tail_sync(chat_id: int, task_key: str, pending_items: list[dict]) -> None:
    """Parent queue: UI item dicts not yet dispatched to ``apply_to_vacancies_batch_ui_task``."""
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    key = autorespond_ui_tail_key(chat_id, task_key)
    try:
        if not pending_items:
            r.delete(key)
        else:
            r.set(key, json.dumps({"items": pending_items}), ex=_DONE_TTL_S)
    finally:
        r.close()


def load_autorespond_ui_tail_sync(chat_id: int, task_key: str) -> list[dict] | None:
    """Load parent pending UI rows for refresh between child batches."""
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    key = autorespond_ui_tail_key(chat_id, task_key)
    try:
        raw = r.get(key)
        if not raw:
            return None
        data = json.loads(raw)
        items = data.get("items")
        if not isinstance(items, list):
            return None
        out = [x for x in items if isinstance(x, dict)]
        return out if out else None
    finally:
        r.close()


def clear_autorespond_ui_tail_sync(chat_id: int, task_key: str) -> None:
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        r.delete(autorespond_ui_tail_key(chat_id, task_key))
    finally:
        r.close()


def set_autorespond_parent_loop_active_sync(chat_id: int, task_key: str) -> None:
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        r.set(autorespond_parent_loop_key(chat_id, task_key), "1", ex=_DONE_TTL_S)
    finally:
        r.close()


def clear_autorespond_parent_loop_active_sync(chat_id: int, task_key: str) -> None:
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        r.delete(autorespond_parent_loop_key(chat_id, task_key))
    finally:
        r.close()


def is_autorespond_parent_loop_active_sync(chat_id: int, task_key: str) -> bool:
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        return bool(r.get(autorespond_parent_loop_key(chat_id, task_key)))
    finally:
        r.close()


def pop_autorespond_ui_tail_batch_sync(
    chat_id: int,
    task_key: str,
    batch_size: int,
) -> list[dict]:
    """Atomically remove up to ``batch_size`` items from the parent tail; return popped rows."""
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    key = autorespond_ui_tail_key(chat_id, task_key)
    try:
        for _ in range(30):
            try:
                r.watch(key)
                raw = r.get(key)
                if not raw:
                    r.unwatch()
                    return []
                data = json.loads(raw)
                items = data.get("items")
                if not isinstance(items, list):
                    r.unwatch()
                    return []
                clean = [x for x in items if isinstance(x, dict)]
                if not clean:
                    r.unwatch()
                    return []
                take = min(batch_size, len(clean))
                batch = clean[:take]
                rest = clean[take:]
                p = r.pipeline()
                p.multi()
                if not rest:
                    p.delete(key)
                else:
                    p.set(key, json.dumps({"items": rest}), ex=_DONE_TTL_S)
                p.execute()
                return batch
            except WatchError:
                continue
        logger.warning(
            "pop_autorespond_ui_tail_batch_sync_gave_up",
            chat_id=chat_id,
            task_key=task_key,
        )
        return []
    finally:
        r.close()


def clear_hh_ui_batch_checkpoint_sync(chat_id: int, task_key: str) -> None:
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        r.delete(hh_ui_batch_checkpoint_key(chat_id, task_key))
    finally:
        r.close()


def increment_autorespond_failed_sync(chat_id: int, task_key: str, n: int = 1) -> int:
    """Increment failed counter (sync Redis; safe from Celery before async tick)."""
    if n <= 0:
        return 0
    r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
    key = autorespond_failed_redis_key(chat_id, task_key)
    try:
        v = int(r.incrby(key, n))
        r.expire(key, _DONE_TTL_S)
        return v
    finally:
        r.close()


def is_autorespond_cancelled_sync(chat_id: int, task_key: str) -> bool:
    """Set by the progress Cancel button; checked by Celery child tasks (sync Redis).

    If Redis is unreachable (DNS, network, broker down), returns False so autorespond
    continues; cancel cannot be observed until Redis works again.
    """
    key = autorespond_cancel_redis_key(chat_id, task_key)
    r: sync_redis.Redis | None = None
    try:
        r = sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)
        return bool(r.get(key))
    except RedisError as exc:
        logger.warning(
            "autorespond_cancel_check_redis_failed",
            chat_id=chat_id,
            task_key=task_key,
            error=str(exc),
        )
        return False
    finally:
        if r is not None:
            r.close()


async def set_autorespond_cancelled(chat_id: int, task_key: str) -> None:
    """Mark autorespond run as cancelled (child tasks exit without applying)."""
    redis = create_progress_redis()
    try:
        await redis.set(autorespond_cancel_redis_key(chat_id, task_key), "1", ex=_DONE_TTL_S)
    finally:
        await redis.aclose()


async def clear_autorespond_done_counter(chat_id: int, task_key: str) -> None:
    redis = create_progress_redis()
    await redis.delete(autorespond_done_redis_key(chat_id, task_key))


async def clear_autorespond_failed_counter(chat_id: int, task_key: str) -> None:
    redis = create_progress_redis()
    await redis.delete(autorespond_failed_redis_key(chat_id, task_key))


async def _rehydrate_autorespond_progress_task_if_missing(
    *,
    redis,
    svc: ProgressService,
    chat_id: int,
    task_key: str,
    total: int,
    locale: str,
    title: str | None,
    celery_task_id: str | None,
) -> bool:
    """If ProgressService task JSON is missing, run ``start_task``. Returns True if rehydrated."""
    state_key = f"progress:task:{chat_id}:{task_key}"
    if await redis.get(state_key):
        return False
    logger.info(
        "autorespond_progress_rehydrating_task_state",
        chat_id=chat_id,
        task_key=task_key,
        total=total,
    )
    nid = normalize_celery_task_id(celery_task_id) if celery_task_id else None
    bar_lbl = get_text("progress-bar-autorespond", locale)
    await svc.start_task(
        task_key=task_key,
        title=title or bar_lbl,
        bar_labels=[bar_lbl],
        celery_task_id=nid,
        initial_totals=[total],
    )
    return True


async def ensure_autorespond_progress_task_state_if_missing(
    *,
    bot: Any,
    chat_id: int,
    autorespond_progress: dict,
    locale: str,
) -> None:
    """When HH UI batch starts: recreate pinned progress if Redis TTL dropped task state.

    Without this, the bar only appears after the first vacancy finalizes (first ``tick``).
    """
    if not autorespond_progress or not autorespond_progress.get("task_key"):
        return
    total = int(autorespond_progress.get("total") or 0)
    if total <= 0:
        return
    task_key = str(autorespond_progress["task_key"])
    title = autorespond_progress.get("title")
    celery_task_id = autorespond_progress.get("celery_task_id")
    loc = str(autorespond_progress.get("locale") or locale)

    redis = create_progress_redis()
    try:
        svc = ProgressService(bot, chat_id, redis, loc)
        rehydrated = await _rehydrate_autorespond_progress_task_if_missing(
            redis=redis,
            svc=svc,
            chat_id=chat_id,
            task_key=task_key,
            total=total,
            locale=loc,
            title=title if isinstance(title, str) else None,
            celery_task_id=celery_task_id if isinstance(celery_task_id, str) else None,
        )
        if not rehydrated:
            return
        done_key = autorespond_done_redis_key(chat_id, task_key)
        done = int(await redis.get(done_key) or 0)
        display_done = min(done, total)
        failed_n = int(await redis.get(autorespond_failed_redis_key(chat_id, task_key)) or 0)
        footer_lines = [get_text("autorespond-progress-failed", loc, count=failed_n)]
        try:
            await svc.update_bar(task_key, 0, display_done, total)
            await svc.update_footer(task_key, footer_lines)
        except Exception as exc:
            logger.warning(
                "ensure_autorespond_progress_bar_failed",
                error=str(exc)[:400],
                chat_id=chat_id,
                task_key=task_key,
            )
    finally:
        await redis.aclose()


async def tick_autorespond_bar(
    *,
    bot: Any,
    chat_id: int,
    task_key: str,
    total: int,
    locale: str,
    footer_failed_line: str | None = None,
    title: str | None = None,
    celery_task_id: str | None = None,
) -> bool:
    """Increment done counter, refresh bar, finish pinned progress when done >= total.

    Returns True if the autorespond progress task was finished (all steps accounted for).
    """
    if total <= 0:
        return False

    redis = create_progress_redis()
    try:
        svc = ProgressService(bot, chat_id, redis, locale)
        await _rehydrate_autorespond_progress_task_if_missing(
            redis=redis,
            svc=svc,
            chat_id=chat_id,
            task_key=task_key,
            total=total,
            locale=locale,
            title=title,
            celery_task_id=celery_task_id,
        )

        key = autorespond_done_redis_key(chat_id, task_key)
        done = int(await redis.incr(key))
        await redis.expire(key, _DONE_TTL_S)

        display_done = min(done, total)

        if footer_failed_line is not None:
            footer_lines = [footer_failed_line]
        else:
            failed_n = int(
                await redis.get(autorespond_failed_redis_key(chat_id, task_key)) or 0
            )
            footer_lines = [get_text("autorespond-progress-failed", locale, count=failed_n)]
        try:
            await svc.update_bar(task_key, 0, display_done, total)
            await svc.update_footer(task_key, footer_lines)
        except Exception as exc:
            # Telegram / aiohttp timeouts or SSL stalls must not abort autorespond (SoftTimeLimitExceeded).
            logger.warning(
                "autorespond_progress_bar_update_failed",
                error=str(exc)[:400],
                chat_id=chat_id,
                task_key=task_key,
            )

        if done >= total:
            failed_n = int(await redis.get(autorespond_failed_redis_key(chat_id, task_key)) or 0)
            logger.info(
                "autorespond_progress_finish_task",
                chat_id=chat_id,
                task_key=task_key,
                done=done,
                total=total,
                failed_ui=failed_n,
            )
            finish_note = None
            if failed_n > 0:
                finish_note = get_text(
                    "autorespond-progress-completed-with-failures",
                    locale,
                    count=failed_n,
                )
            try:
                await svc.finish_task(task_key, shortage_note=finish_note)
            except Exception as exc:
                logger.warning(
                    "autorespond_progress_finish_failed",
                    error=str(exc)[:400],
                    chat_id=chat_id,
                    task_key=task_key,
                )
            await redis.delete(key)
            await redis.delete(autorespond_failed_redis_key(chat_id, task_key))
            # Parent ``run_autorespond`` used to clear these as soon as it finished
            # dispatching ``.delay()`` batches, while hh_ui children were still running.
            # That deleted ``resume`` + empty ``items`` checkpoints and broke refresh merge;
            # clear only when every work unit has ticked (done >= total).
            clear_hh_ui_batch_checkpoint_sync(chat_id, task_key)
            clear_hh_ui_resume_envelope_sync(chat_id, task_key)
            clear_autorespond_ui_tail_sync(chat_id, task_key)
            return True
        return False
    finally:
        await redis.aclose()
