"""Minimal ASGI app for HeadHunter OAuth redirect callback.

Run: uvicorn src.oauth_app:app --host 0.0.0.0 --port 8090

Put the same URL in HH app settings as HH_OAUTH_REDIRECT_URI and reverse-proxy with TLS.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse
from starlette.routing import Route

from src.config import settings
from src.db.engine import async_session_factory
from src.repositories.hh_linked_account import HhLinkedAccountRepository
from src.repositories.user import UserRepository
from src.services.hh.client import HhApiClient
from src.services.hh.crypto import HhTokenCipher
from src.services.hh.oauth_state import pop_telegram_user_id
from src.services.hh.oauth_tokens import exchange_code_for_tokens

logger = logging.getLogger(__name__)


def _utc_naive_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def hh_oauth_callback(request: Request) -> HTMLResponse | PlainTextResponse:
    if not settings.hh_client_id or not settings.hh_token_encryption_key:
        return PlainTextResponse("HeadHunter OAuth is not configured", status_code=503)

    err = request.query_params.get("error")
    if err == "access_denied":
        return HTMLResponse(
            "<html><body><p>Доступ отклонён. Закройте вкладку и вернитесь в Telegram.</p></body></html>",
            status_code=200,
        )
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code or not state:
        return PlainTextResponse("Missing code or state", status_code=400)

    telegram_user_id = await pop_telegram_user_id(state)
    if telegram_user_id is None:
        return PlainTextResponse("Invalid or expired state", status_code=400)

    try:
        token_payload = await exchange_code_for_tokens(code=code)
    except Exception:
        logger.exception("HH OAuth token exchange failed")
        return PlainTextResponse("Token exchange failed", status_code=502)

    access_token = token_payload["access_token"]
    refresh_token = token_payload["refresh_token"]
    expires_in = int(token_payload.get("expires_in", 3600))

    cipher = HhTokenCipher(settings.hh_token_encryption_key)
    api = HhApiClient(access_token)
    try:
        me = await api.get_me()
    except Exception:
        logger.exception("HH OAuth get_me failed after token exchange")
        return PlainTextResponse("Failed to load HH profile", status_code=502)

    hh_uid = str(me.get("id", ""))
    if not hh_uid:
        return PlainTextResponse("HH profile has no id", status_code=502)

    first = (me.get("first_name") or "").strip()
    last = (me.get("last_name") or "").strip()
    default_label = f"{first} {last}".strip() or None

    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_user_id)
        if not user:
            return PlainTextResponse("Telegram user not found", status_code=404)

        acc_repo = HhLinkedAccountRepository(session)
        existing = await acc_repo.get_by_user_and_hh_user_id(user.id, hh_uid)
        exp_at = _utc_naive_now() + timedelta(seconds=max(120, expires_in - 120))
        if existing:
            label = existing.label or default_label
            await acc_repo.update(
                existing,
                label=label,
                access_token_enc=cipher.encrypt(access_token),
                refresh_token_enc=cipher.encrypt(refresh_token),
                access_expires_at=exp_at,
                revoked_at=None,
                last_used_at=_utc_naive_now(),
            )
        else:
            await acc_repo.create(
                user_id=user.id,
                hh_user_id=hh_uid,
                label=default_label,
                access_token_enc=cipher.encrypt(access_token),
                refresh_token_enc=cipher.encrypt(refresh_token),
                access_expires_at=exp_at,
                revoked_at=None,
                last_used_at=_utc_naive_now(),
            )
        await session.commit()

    return HTMLResponse(
        "<html><body><p>Аккаунт hh.ru подключён. Вернитесь в Telegram.</p></body></html>",
        status_code=200,
    )


routes = [Route("/oauth/hh/callback", hh_oauth_callback, methods=["GET"])]
app = Starlette(routes=routes)
