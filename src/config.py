from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from pydantic import AliasChoices, Field, model_validator
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

    # Logging — append-only ``log_dir/hh_bot.log`` (no rotation; see ``setup_logging``); mount ``./logs`` in Docker.
    log_level: str = "INFO"
    log_dir: Path = Field(
        default_factory=lambda: BASE_DIR / "logs",
        validation_alias=AliasChoices("HH_BOT_LOG_DIR", "log_dir"),
    )
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
    # Random delay between public API search (GET /vacancies) requests — reduces rate spikes.
    hh_public_api_list_delay_min_seconds: float = Field(default=0.25, ge=0.0, le=60.0)
    hh_public_api_list_delay_max_seconds: float = Field(default=0.65, ge=0.0, le=60.0)
    # Random delay before each GET /vacancies/{id} (detail) request.
    hh_public_api_vacancy_delay_min_seconds: float = Field(default=0.12, ge=0.0, le=60.0)
    hh_public_api_vacancy_delay_max_seconds: float = Field(default=0.45, ge=0.0, le=60.0)
    # Parallel GET /vacancies/{id} (public API) — lower reduces 403 risk from HH edge.
    hh_vacancy_detail_concurrency: int = Field(default=5, ge=1, le=30)
    # Autoparse: detail+AI+DB vertical batch size; 0 = use hh_vacancy_detail_concurrency.
    hh_autoparse_pipeline_batch_size: int = Field(default=0, ge=0, le=30)
    # Optional pause between autoparse pipeline batches (after AI+DB, before next detail batch).
    hh_autoparse_inter_batch_sleep_seconds: float = Field(default=0.0, ge=0.0, le=120.0)
    # After HH captcha_required (403), block further public API calls until cooldown (Redis CB).
    # Default 300 aligns with Celery captcha retry cap so retries are not scheduled too early.
    hh_public_api_circuit_recovery_seconds: int = Field(default=300, ge=60, le=86400)
    # Exponential recovery: each open multiplies wait by recovery_multiplier (capped).
    hh_public_api_circuit_recovery_max_seconds: int = Field(default=3600, ge=60, le=86400)
    hh_public_api_circuit_recovery_multiplier: float = Field(default=2.0, ge=1.0, le=10.0)
    hh_public_api_circuit_failure_threshold: int = Field(default=3, ge=1, le=20)
    # HTTP 403/429 (non-captcha): exp. backoff, then Playwright; few HTTP tries before web.
    hh_public_api_403_retry_base_seconds: float = Field(default=2.0, ge=0.5, le=60.0)
    hh_public_api_403_retry_max_seconds: float = Field(default=60.0, ge=1.0, le=300.0)
    hh_public_api_rate_limit_max_attempts_detail: int = Field(default=3, ge=1, le=10)
    hh_public_api_rate_limit_max_attempts_search: int = Field(default=5, ge=1, le=30)
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
    # Batched UI apply: one Chromium session per chunk (see ``hh_ui.apply_to_vacancies_batch``).
    hh_ui_apply_batch_size: int = Field(default=4, ge=1, le=50)
    hh_ui_apply_batch_task_soft_time_limit: int = Field(default=2400, ge=300, le=14400)
    hh_ui_apply_batch_task_time_limit: int = Field(default=3000, ge=600, le=18000)
    hh_ui_apply_max_retries: int = Field(default=5, ge=1, le=10)
    hh_ui_apply_retry_initial_seconds: float = Field(default=10.0, ge=1.0, le=300.0)
    hh_ui_apply_retry_delay_cap_seconds: float = Field(default=600.0, ge=10.0, le=3600.0)
    # Celery ``autoparse.run_company``: large target_count runs need hours; wall-clock is total budget.
    # Redis per-company run lock TTL is renewed on an interval (see autoparse task) — not the same as stall detection.
    autoparse_run_company_soft_time_limit_seconds: int = Field(default=14400, ge=300, le=86400)
    autoparse_run_company_time_limit_seconds: int = Field(default=15300, ge=600, le=93600)
    # Sliding window for ``lock:autoparse:run:{company_id}`` — extended while the task heartbeats.
    autoparse_run_company_lock_ttl_seconds: int = Field(default=1800, ge=300, le=86400)
    autoparse_run_company_lock_renew_interval_seconds: int = Field(default=120, ge=30, le=3600)
    # DB-synced via admin toggle (see AppSettingKey.HH_UI_DEBUG_PLAYWRIGHT_SCREENSHOTS)
    hh_ui_debug_playwright_screenshots: bool = False
    negotiations_sync_fetch_vacancy_details: bool = False
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
        userinfo = f"{quote(self.postgres_user, safe='')}:{quote(self.postgres_password, safe='')}"
        return (
            f"postgresql+asyncpg://{userinfo}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        userinfo = f"{quote(self.postgres_user, safe='')}:{quote(self.postgres_password, safe='')}"
        return (
            f"postgresql://{userinfo}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
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
        if self.hh_ui_apply_batch_task_time_limit <= self.hh_ui_apply_batch_task_soft_time_limit:
            raise ValueError(
                "hh_ui_apply_batch_task_time_limit must be greater than "
                "hh_ui_apply_batch_task_soft_time_limit"
            )
        if self.hh_public_api_list_delay_max_seconds < self.hh_public_api_list_delay_min_seconds:
            raise ValueError(
                "hh_public_api_list_delay_max_seconds must be >= hh_public_api_list_delay_min_seconds"
            )
        if self.hh_public_api_vacancy_delay_max_seconds < self.hh_public_api_vacancy_delay_min_seconds:
            raise ValueError(
                "hh_public_api_vacancy_delay_max_seconds must be >= hh_public_api_vacancy_delay_min_seconds"
            )
        if self.autoparse_run_company_time_limit_seconds <= self.autoparse_run_company_soft_time_limit_seconds:
            raise ValueError(
                "autoparse_run_company_time_limit_seconds must be greater than "
                "autoparse_run_company_soft_time_limit_seconds"
            )
        if self.autoparse_run_company_lock_ttl_seconds < self.autoparse_run_company_lock_renew_interval_seconds * 2:
            raise ValueError(
                "autoparse_run_company_lock_ttl_seconds should be at least twice "
                "autoparse_run_company_lock_renew_interval_seconds so renewals keep the lock alive"
            )
        if self.hh_public_api_403_retry_max_seconds < self.hh_public_api_403_retry_base_seconds:
            raise ValueError(
                "hh_public_api_403_retry_max_seconds must be >= "
                "hh_public_api_403_retry_base_seconds"
            )
        max_cb = self.hh_public_api_circuit_recovery_max_seconds
        base_cb = self.hh_public_api_circuit_recovery_seconds
        if max_cb < base_cb:
            raise ValueError(
                "hh_public_api_circuit_recovery_max_seconds must be >= "
                "hh_public_api_circuit_recovery_seconds"
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
