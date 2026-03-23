from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    bot_token: str

    # PostgreSQL
    postgres_user: str = "hh_bot"
    postgres_password: str = "hh_bot_secret"
    postgres_db: str = "hh_bot"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # OpenAI
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    # Logging
    log_level: str = "INFO"
    log_telegram_chat_id: str = ""
    support_chat_id: str = ""

    # Admin — comma-separated Telegram user IDs for initial admin seeding
    admin_telegram_ids: str = ""

    # HeadHunter OAuth (https://api.hh.ru/openapi/redoc)
    hh_client_id: str = ""
    hh_client_secret: str = ""
    hh_oauth_redirect_uri: str = ""
    hh_user_agent: str = "HHBot/1.0 (dev@localhost)"
    hh_token_encryption_key: str = ""

    # HeadHunter UI apply (Playwright) — optional; off by default
    hh_ui_apply_enabled: bool = False
    hh_ui_apply_max_per_day: int = 50
    hh_ui_navigation_timeout_ms: int = 60000
    hh_ui_action_timeout_ms: int = 30000
    hh_ui_min_action_delay_ms: int = 300
    hh_ui_max_action_delay_ms: int = 1200
    hh_ui_headless: bool = True
    hh_ui_screenshot_on_error: bool = False

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def admin_ids(self) -> list[int]:
        if not self.admin_telegram_ids:
            return []
        return [int(x.strip()) for x in self.admin_telegram_ids.split(",") if x.strip()]


settings = Settings()  # type: ignore[call-arg]


def sync_setting_to_runtime(key: str, value: object) -> None:
    """Push a single DB-managed setting value into the runtime settings object."""
    if not hasattr(settings, key):
        return
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    setattr(settings, key, str(value) if not isinstance(value, str) else value)
