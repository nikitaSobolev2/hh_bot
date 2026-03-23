"""Encrypt/decrypt Playwright storage_state JSON using the same Fernet key as HH tokens."""

from __future__ import annotations

import json
from typing import Any

from src.services.hh.crypto import HhTokenCipher


def encrypt_browser_storage(state: dict[str, Any], cipher: HhTokenCipher) -> bytes:
    payload = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    return cipher.encrypt(payload)


def decrypt_browser_storage(data: bytes | None, cipher: HhTokenCipher) -> dict[str, Any] | None:
    if not data:
        return None
    raw = cipher.decrypt_to_str(data)
    return json.loads(raw)
