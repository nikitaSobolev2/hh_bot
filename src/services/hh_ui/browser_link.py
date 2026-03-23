"""Validate Playwright storage_state JSON and derive hh.ru account id for linking without OAuth."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime
from typing import Any

from src.services.hh.crypto import HhTokenCipher
from src.services.hh_ui.storage import encrypt_browser_storage


def placeholder_access_expires_at() -> datetime:
    """Far-future expiry so REST token refresh is not attempted for browser-only rows."""
    return datetime(2100, 1, 1, 0, 0, 0)


def placeholder_token_ciphertexts(cipher: HhTokenCipher) -> tuple[bytes, bytes]:
    """Dummy OAuth token blobs for rows that only use Playwright + browser storage."""
    placeholder = "__hh_browser_ui_no_oauth__"
    blob = cipher.encrypt(placeholder)
    return blob, blob


def validate_playwright_storage_state(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ValueError("not-a-json-object")
    cookies = obj.get("cookies")
    if not isinstance(cookies, list):
        raise ValueError("missing-cookies-array")
    has_hh = any(
        isinstance(c, dict) and "hh.ru" in str(c.get("domain", "")).lower()
        for c in cookies
    )
    if not has_hh:
        raise ValueError("no-hh-cookies")
    return obj


def _jwt_sub_or_id(token: str) -> str | None:
    try:
        parts = token.strip().split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1]
        pad = "=" * (-len(payload_b64) % 4)
        raw = base64.urlsafe_b64decode(payload_b64 + pad)
        data = json.loads(raw)
        for key in ("sub", "user_id", "id"):
            v = data.get(key)
            if v is not None:
                s = str(v).strip()
                if s.isdigit():
                    return s
        return None
    except Exception:
        return None


def _hh_cookie_user_id(cookie: dict[str, Any]) -> str | None:
    domain = str(cookie.get("domain", "")).lower()
    if "hh.ru" not in domain:
        return None
    name = (cookie.get("name") or "").lower()
    val = str(cookie.get("value") or "")
    if name in ("uid", "user_id", "hhuid", "huid") and val.isdigit():
        return val
    if name == "hhtoken" and val:
        return _jwt_sub_or_id(val)
    return None


def guess_hh_user_id_from_storage(state: dict[str, Any]) -> str | None:
    for c in state.get("cookies") or []:
        if not isinstance(c, dict):
            continue
        uid = _hh_cookie_user_id(c)
        if uid:
            return uid
    return None


def make_hh_user_id_for_browser_link(state: dict[str, Any]) -> str:
    guessed = guess_hh_user_id_from_storage(state)
    if guessed:
        return guessed
    return f"browser_{uuid.uuid4().hex[:16]}"


def is_logged_in_storage_state(state: dict[str, Any]) -> bool:
    """True if cookies suggest an authenticated hh.ru session (not just landing cookies)."""
    if guess_hh_user_id_from_storage(state):
        return True
    for c in state.get("cookies") or []:
        if not isinstance(c, dict):
            continue
        if "hh.ru" not in str(c.get("domain", "")).lower():
            continue
        name = (c.get("name") or "").lower()
        val = str(c.get("value") or "").strip()
        if name == "hhtoken" and len(val) > 10:
            return True
    return False


def encrypt_storage_for_account(state: dict[str, Any], cipher: HhTokenCipher) -> bytes:
    return encrypt_browser_storage(state, cipher)
