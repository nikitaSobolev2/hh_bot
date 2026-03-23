"""Celery task: server-side Playwright login assist for hh.ru (storage_state → DB)."""

from __future__ import annotations

import asyncio
import contextlib

import redis as sync_redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import settings
from src.core.i18n import get_text
from src.services.hh.crypto import HhTokenCipher
from src.services.hh.linked_account_browser_storage import persist_browser_storage_state_for_user
from src.services.hh_ui.login_assist_rate_limit import try_acquire_login_assist_slot_sync
from src.services.hh_ui.login_assist_runner import (
    HhLoginAssistRunnerConfig,
    LoginAssistOutcome,
    run_login_assist_sync,
)
from src.worker.app import celery_app
from src.worker.base_task import HHBotTask
from src.worker.utils import run_async

_ACTIVE_KEY = "hh_login_assist:active:{user_id}"


def _redis() -> sync_redis.Redis:
    return sync_redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _store_active_job(user_id: int, celery_task_id: str, ttl_seconds: int) -> None:
    r = _redis()
    try:
        r.setex(_ACTIVE_KEY.format(user_id=user_id), ttl_seconds, celery_task_id)
    finally:
        r.close()


def _clear_active_job(user_id: int) -> None:
    r = _redis()
    try:
        r.delete(_ACTIVE_KEY.format(user_id=user_id))
    finally:
        r.close()


def clear_active_job_for_user(user_id: int) -> None:
    """Public helper for bot cancel handler."""
    _clear_active_job(user_id)


def get_active_job_id(user_id: int) -> str | None:
    r = _redis()
    try:
        v = r.get(_ACTIVE_KEY.format(user_id=user_id))
        return str(v) if v else None
    finally:
        r.close()


async def _login_assist_async(
    self: HHBotTask,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
) -> dict:
    log = self.get_logger().bind(user_id=user_id, celery_id=self.request.id or "?")
    bot = self.create_bot()

    if not settings.hh_login_assist_enabled:
        with contextlib.suppress(Exception):
            await self.notify_user(
                bot, chat_id, message_id, get_text("hh-login-assist-disabled", locale)
            )
        return {"status": "disabled"}

    if not settings.hh_ui_apply_enabled or not settings.hh_token_encryption_key:
        with contextlib.suppress(Exception):
            await self.notify_user(
                bot, chat_id, message_id, get_text("hh-login-assist-not-configured", locale)
            )
        return {"status": "not_configured"}

    if not await self.acquire_user_task_lock(
        user_id, "hh_login_assist", ttl=int(settings.hh_login_assist_max_wait_seconds) + 180
    ):
        with contextlib.suppress(Exception):
            await self.notify_user(
                bot, chat_id, message_id, get_text("hh-login-assist-parallel", locale)
            )
        return {"status": "parallel"}

    if not try_acquire_login_assist_slot_sync(user_id):
        await self.release_user_task_lock(user_id, "hh_login_assist")
        with contextlib.suppress(Exception):
            await self.notify_user(
                bot, chat_id, message_id, get_text("hh-login-assist-rate-limited", locale)
            )
        return {"status": "rate_limited"}

    ttl = int(settings.hh_login_assist_max_wait_seconds) + 120
    if self.request.id:
        _store_active_job(user_id, str(self.request.id), ttl)

    cfg = HhLoginAssistRunnerConfig.from_settings()

    try:
        with contextlib.suppress(Exception):
            await self.notify_user(
                bot, chat_id, message_id, get_text("hh-login-assist-queued", locale)
            )

        viewer = (settings.hh_login_assist_viewer_url or "").strip()
        if viewer:
            with contextlib.suppress(Exception):
                await self.notify_user(
                    bot,
                    chat_id,
                    message_id,
                    get_text("hh-login-assist-browser-open", locale, url=viewer),
                )
        else:
            with contextlib.suppress(Exception):
                await self.notify_user(
                    bot,
                    chat_id,
                    message_id,
                    get_text("hh-login-assist-no-viewer", locale),
                )

        state_dict, outcome, err_detail = await asyncio.to_thread(run_login_assist_sync, cfg)

        if outcome == LoginAssistOutcome.SUCCESS and state_dict:
            with contextlib.suppress(Exception):
                await self.notify_user(
                    bot, chat_id, message_id, get_text("hh-login-assist-saving", locale)
                )
            cipher = HhTokenCipher(settings.hh_token_encryption_key)
            async with session_factory() as session:
                await persist_browser_storage_state_for_user(
                    session, user_id, state_dict, cipher=cipher
                )
                await session.commit()
            log.info("hh_login_assist persisted", outcome="success")
            with contextlib.suppress(Exception):
                await self.notify_user(
                    bot, chat_id, message_id, get_text("hh-login-assist-success", locale)
                )
            return {"status": "success"}

        if outcome == LoginAssistOutcome.CAPTCHA:
            log.warning("hh_login_assist captcha")
            with contextlib.suppress(Exception):
                await self.notify_user(
                    bot, chat_id, message_id, get_text("hh-login-assist-captcha", locale)
                )
            return {"status": "captcha"}

        if outcome == LoginAssistOutcome.TIMEOUT:
            log.warning("hh_login_assist timeout", detail=err_detail)
            with contextlib.suppress(Exception):
                await self.notify_user(
                    bot, chat_id, message_id, get_text("hh-login-assist-timeout", locale)
                )
            return {"status": "timeout"}

        log.error("hh_login_assist error", detail=err_detail)
        with contextlib.suppress(Exception):
            await self.notify_user(
                bot,
                chat_id,
                message_id,
                get_text("hh-login-assist-error", locale, detail=err_detail or "error"),
            )
        return {"status": "error", "detail": err_detail}

    finally:
        _clear_active_job(user_id)
        with contextlib.suppress(Exception):
            await self.release_user_task_lock(user_id, "hh_login_assist")
        with contextlib.suppress(Exception):
            await bot.session.close()


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="hh.login_assist",
    queue="login_assist",
    soft_time_limit=960,
    time_limit=1020,
)
def hh_login_assist_task(
    self: HHBotTask,
    user_id: int,
    chat_id: int,
    message_id: int,
    locale: str,
) -> dict:
    return run_async(
        lambda sf: _login_assist_async(self, sf, user_id, chat_id, message_id, locale)
    )
