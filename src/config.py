from __future__ import annotations

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
# Default dir for admin “debug Playwright screenshots” (mount a volume here in Docker).
_DEFAULT_PLAYWRIGHT_DEBUG_DIR = BASE_DIR / "data" / "playwright_debug"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        # Managed in Admin → App settings (DB), not .env
        env_ignore=("HH_UI_APPLY_MAX_PER_DAY",),
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

    # DB-synced via admin (see sync_setting_to_runtime); default when unset in DB
    task_autorespond_enabled: bool = False

    # HeadHunter OAuth (https://api.hh.ru/openapi/redoc)
    hh_client_id: str = ""
    hh_client_secret: str = ""
    hh_oauth_redirect_uri: str = ""
    hh_user_agent: str = "HHBot/1.0 (dev@localhost)"
    # Parallel GET /vacancies/{id} (public API) — lower reduces 403 risk from HH edge.
    hh_vacancy_detail_concurrency: int = Field(default=5, ge=1, le=30)
    # After HH captcha_required (403), block further public API calls until cooldown (Redis CB).
    hh_public_api_circuit_recovery_seconds: int = Field(default=900, ge=60, le=86400)
    hh_token_encryption_key: str = ""

    # HeadHunter UI apply (Playwright) — optional; off by default
    hh_ui_apply_enabled: bool = False
    # Daily cap per user (UTC): set via Admin → App settings (also synced to workers on startup).
    hh_ui_apply_max_per_day: int = 50
    hh_ui_navigation_timeout_ms: int = 60000
    hh_ui_action_timeout_ms: int = 30000
    hh_ui_min_action_delay_ms: int = 300
    hh_ui_max_action_delay_ms: int = 1200
    hh_ui_headless: bool = True
    hh_ui_screenshot_on_error: bool = False
    # Prefer POST /applicant/vacancy_response/popup via in-page fetch before modal automation.
    hh_ui_apply_use_popup_api: bool = True
    # Celery wall-clock limits for ``hh_ui.apply_to_vacancy`` (Playwright; may wait on slow pages).
    hh_ui_apply_task_soft_time_limit: int = Field(default=480, ge=60, le=3600)
    hh_ui_apply_task_time_limit: int = Field(default=600, ge=120, le=7200)
    # DB-synced via admin toggle (see AppSettingKey.HH_UI_DEBUG_PLAYWRIGHT_SCREENSHOTS)
    hh_ui_debug_playwright_screenshots: bool = False
    hh_ui_debug_screenshot_dir: str = str(_DEFAULT_PLAYWRIGHT_DEBUG_DIR)

    # HH server-side login assist (Playwright; optional noVNC — docs/HH_LOGIN_ASSIST.md)
    hh_login_assist_enabled: bool = False
    hh_login_assist_max_wait_seconds: int = 900
    hh_login_assist_poll_interval_seconds: float = 2.0
    hh_login_assist_max_per_day: int = 5
    hh_login_assist_login_url: str = "https://hh.ru/account/login"
    hh_login_assist_viewer_url: str = ""
    hh_login_assist_headless: bool = True

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

    @model_validator(mode="after")
    def _hh_ui_apply_task_limits_order(self) -> Settings:
        if self.hh_ui_apply_task_time_limit <= self.hh_ui_apply_task_soft_time_limit:
            raise ValueError(
                "hh_ui_apply_task_time_limit must be greater than hh_ui_apply_task_soft_time_limit"
            )
        return self


settings = Settings()  # type: ignore[call-arg]


def sync_setting_to_runtime(key: str, value: object) -> None:
    """Push a single DB-managed setting value into the runtime settings object."""
    if not hasattr(settings, key):
        return
    if isinstance(value, bool):
        setattr(settings, key, value)
        return
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        setattr(settings, key, int(value))
        return
    current = getattr(settings, key)
    if isinstance(current, int) and isinstance(value, str) and value.strip() != "":
        try:
            setattr(settings, key, int(value.strip()))
        except ValueError:
            setattr(settings, key, value)
        return
    setattr(settings, key, str(value) if not isinstance(value, str) else value)
