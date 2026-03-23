"""Tests for HeadHunter token encryption."""

from cryptography.fernet import Fernet

from src.services.hh.crypto import HhTokenCipher, generate_fernet_key


def test_hh_token_cipher_roundtrip() -> None:
    key = Fernet.generate_key().decode("ascii")
    cipher = HhTokenCipher(key)
    plain = "access-token-abc"
    assert cipher.decrypt_to_str(cipher.encrypt(plain)) == plain


def test_generate_fernet_key_is_valid() -> None:
    key = generate_fernet_key()
    cipher = HhTokenCipher(key)
    assert cipher.encrypt("x") != cipher.encrypt("y")
