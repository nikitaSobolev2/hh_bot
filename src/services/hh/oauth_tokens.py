"""HeadHunter OAuth2 token endpoint (authorization code and refresh)."""

from __future__ import annotations

from typing import Any

import httpx

from src.config import settings

HH_TOKEN_URL = "https://api.hh.ru/token"
HH_AUTH_URL = "https://hh.ru/oauth/authorize"


def build_authorize_url(*, state: str, redirect_uri: str | None = None) -> str:
    from urllib.parse import urlencode

    rid = redirect_uri or settings.hh_oauth_redirect_uri
    q = {
        "response_type": "code",
        "client_id": settings.hh_client_id,
        "state": state,
        "redirect_uri": rid,
        "role": "applicant",
    }
    return f"{HH_AUTH_URL}?{urlencode(q)}"


async def exchange_code_for_tokens(
    *,
    code: str,
    redirect_uri: str | None = None,
) -> dict[str, Any]:
    rid = redirect_uri or settings.hh_oauth_redirect_uri
    data = {
        "grant_type": "authorization_code",
        "client_id": settings.hh_client_id,
        "client_secret": settings.hh_client_secret,
        "code": code,
        "redirect_uri": rid,
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(
            HH_TOKEN_URL,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "HH-User-Agent": settings.hh_user_agent,
            },
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()


async def refresh_tokens(*, refresh_token: str) -> dict[str, Any]:
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": settings.hh_client_id,
        "client_secret": settings.hh_client_secret,
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(
            HH_TOKEN_URL,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "HH-User-Agent": settings.hh_user_agent,
            },
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()
