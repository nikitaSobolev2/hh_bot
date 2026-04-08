"""Database URL userinfo must tolerate special characters in credentials."""

from urllib.parse import unquote, urlparse

from src.config import Settings


def test_database_urls_percent_encode_user_and_password() -> None:
    s = Settings(
        bot_token="x",
        postgres_user="user@realm",
        postgres_password="p:ass@word/1",
        postgres_db="hh_bot",
        postgres_host="localhost",
        postgres_port=5432,
    )
    async_url = s.database_url
    sync_url = s.database_url_sync

    a = urlparse(async_url.replace("postgresql+asyncpg", "postgresql", 1))
    assert unquote(a.username or "") == "user@realm"
    assert unquote(a.password or "") == "p:ass@word/1"
    assert a.hostname == "localhost"
    assert a.port == 5432
    assert a.path == "/hh_bot"

    p = urlparse(sync_url)
    assert unquote(p.username or "") == "user@realm"
    assert unquote(p.password or "") == "p:ass@word/1"
