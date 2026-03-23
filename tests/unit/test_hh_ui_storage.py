"""Tests for HH UI browser storage encryption."""

from cryptography.fernet import Fernet

from src.services.hh.crypto import HhTokenCipher
from src.services.hh_ui.storage import decrypt_browser_storage, encrypt_browser_storage


def test_browser_storage_roundtrip() -> None:
    key = Fernet.generate_key().decode("ascii")
    cipher = HhTokenCipher(key)
    state = {"cookies": [], "origins": [{"origin": "https://hh.ru", "localStorage": []}]}
    enc = encrypt_browser_storage(state, cipher)
    assert decrypt_browser_storage(enc, cipher) == state


def test_decrypt_empty_returns_none() -> None:
    key = Fernet.generate_key().decode("ascii")
    cipher = HhTokenCipher(key)
    assert decrypt_browser_storage(None, cipher) is None
