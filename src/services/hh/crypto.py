from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class HhTokenCipher:
    """Encrypt/decrypt OAuth tokens at rest using Fernet."""

    def __init__(self, key_b64: str) -> None:
        key_b64 = (key_b64 or "").strip()
        if not key_b64:
            raise ValueError("hh_token_encryption_key must be set to a Fernet key")
        self._fernet = Fernet(key_b64.encode("ascii"))

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt_to_str(self, ciphertext: bytes) -> str:
        try:
            return self._fernet.decrypt(ciphertext).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Invalid token ciphertext") from exc


def generate_fernet_key() -> str:
    """Return a url-safe base64 key suitable for HH_TOKEN_ENCRYPTION_KEY."""
    return Fernet.generate_key().decode("ascii")
