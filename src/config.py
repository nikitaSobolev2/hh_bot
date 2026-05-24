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

    # Logging — append-only ``log_dir/hh_bot.log`` (no rotation; see ``setup_logging``);
    # mount ``./logs`` in Docker.
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
    # Deprecated: parent-loop tail chain removed (dispatcher + apply_pump pipeline).
    # Kept for backward-compatible env/config; unused by new autorespond pipeline.
    autorespond_parent_loop_heartbeat_stale_seconds: int = Field(default=120, ge=30, le=600)
    # Autorespond preflight uses httpx only (no Playwright) — avoids blocking the parent worker.
    autorespond_preflight_timeout_seconds: float = Field(default=25.0, ge=5.0, le=120.0)
    autorespond_loop_progress_log_every: int = Field(default=25, ge=1, le=500)
    autorespond_resume_resolve_timeout_seconds: float = Field(
        default=130.0, ge=30.0, le=600.0
    )
    autorespond_progress_tick_timeout_seconds: float = Field(
        default=45.0, ge=5.0, le=120.0
    )
    hh_ui_apply_batch_task_soft_time_limit: int = Field(default=2400, ge=300, le=14400)
    hh_ui_apply_batch_task_time_limit: int = Field(default=3000, ge=600, le=18000)
    # Per-vacancy cap inside ``hh_ui.apply_to_vacancies_batch`` (includes AI retries).
    hh_ui_batch_cover_letter_timeout_seconds: float = Field(default=90.0, ge=10.0, le=600.0)
    # Redis lock for global Chromium slot; renewed while a batch holds the browser.
    playwright_browser_lock_ttl_seconds: int = Field(default=120, ge=60, le=900)
    playwright_browser_lock_renew_interval_seconds: int = Field(default=45, ge=15, le=300)
    playwright_browser_lock_wait_seconds: float = Field(default=180.0, ge=30.0, le=600.0)
    hh_ui_apply_max_retries: int = Field(default=5, ge=1, le=10)
    hh_ui_apply_retry_initial_seconds: float = Field(default=10.0, ge=1.0, le=300.0)
    hh_ui_apply_retry_delay_cap_seconds: float = Field(default=600.0, ge=10.0, le=3600.0)
    # Celery ``autoparse.run_company``: large runs need hours; wall-clock is total budget.
    # Redis per-company run lock TTL is renewed on an interval (see autoparse task) —
    # not the same as stall detection.
    autoparse_run_company_soft_time_limit_seconds: int = Field(default=14400, ge=300, le=86400)
    autoparse_run_company_time_limit_seconds: int = Field(default=15300, ge=600, le=93600)
    # Sliding window for ``lock:autoparse:run:{company_id}`` — extended while the task heartbeats.
    autoparse_run_company_lock_ttl_seconds: int = Field(default=1800, ge=300, le=86400)
    autoparse_run_company_lock_renew_interval_seconds: int = Field(default=120, ge=30, le=3600)
    # DB-synced via admin toggle (see AppSettingKey.HH_UI_DEBUG_PLAYWRIGHT_SCREENSHOTS)
    hh_ui_debug_playwright_screenshots: bool = False
    negotiations_sync_fetch_vacancy_details: bool = False
    # When False, vacancy list + detail scraping use web/Playwright paths only (no public API JSON).
    hh_api_vacancy_parsing_enabled: bool = True
    hh_ui_debug_screenshot_dir: str = str(_DEFAULT_PLAYWRIGHT_DEBUG_DIR)

    # System load throttler (psutil) — autorespond/cover-letter/pump callers back off when host
    # CPU/RAM/disk cross these thresholds. Hysteresis = 5 percentage points below pause threshold.
    system_load_cpu_pause_percent: int = Field(default=92, ge=50, le=100)
    system_load_ram_pause_percent: int = Field(default=90, ge=50, le=100)
    system_load_disk_pause_percent: int = Field(default=97, ge=50, le=100)
    system_load_backoff_max_seconds: int = Field(default=30, ge=1, le=600)

    # Cover-letter pre-generation (queue=cover_letter): one task per vacancy ahead of Playwright.
    cover_letter_pregen_soft_time_limit: int = Field(default=90, ge=10, le=600)
    cover_letter_pregen_time_limit: int = Field(default=120, ge=20, le=900)
    cover_letter_pregen_ttl_seconds: int = Field(default=24 * 3600, ge=300, le=7 * 24 * 3600)

    # Apply pump (queue=hh_ui): long-lived consumer; chains itself before soft-timeout.
    autorespond_apply_pump_soft_time_limit: int = Field(default=600, ge=60, le=14400)
    autorespond_apply_pump_time_limit: int = Field(default=700, ge=120, le=18000)
    # Reserve time at end of pump shift to chain successor before SoftTimeLimit fires.
    autorespond_apply_pump_chain_grace_seconds: int = Field(default=60, ge=10, le=600)
    # Pump waits this long (per item) for a cover letter to arrive in Redis before applying without.
    autorespond_apply_pump_pregen_wait_per_item_seconds: float = Field(
        default=5.0, ge=0.0, le=60.0
    )
    # Pump writes heartbeat at this cadence; recover_stalled treats older heartbeats as dead.
    autorespond_apply_pump_heartbeat_interval_seconds: float = Field(
        default=5.0, ge=1.0, le=60.0
    )
    # recover_stalled: re-enqueue apply_pump if no heartbeat for this long while ready_to_apply > 0.
    autorespond_recover_stalled_pump_grace_seconds: int = Field(default=90, ge=30, le=600)

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
        pw_ttl = self.playwright_browser_lock_ttl_seconds
        pw_renew = self.playwright_browser_lock_renew_interval_seconds
        if pw_ttl < pw_renew * 2:
            raise ValueError(
                "playwright_browser_lock_ttl_seconds should be at least twice "
                "playwright_browser_lock_renew_interval_seconds"
            )
        list_max = self.hh_public_api_list_delay_max_seconds
        list_min = self.hh_public_api_list_delay_min_seconds
        if list_max < list_min:
            raise ValueError(
                "hh_public_api_list_delay_max_seconds must be >= "
                "hh_public_api_list_delay_min_seconds"
            )
        vac_max = self.hh_public_api_vacancy_delay_max_seconds
        vac_min = self.hh_public_api_vacancy_delay_min_seconds
        if vac_max < vac_min:
            raise ValueError(
                "hh_public_api_vacancy_delay_max_seconds must be >= "
                "hh_public_api_vacancy_delay_min_seconds"
            )
        time_lim = self.autoparse_run_company_time_limit_seconds
        soft_lim = self.autoparse_run_company_soft_time_limit_seconds
        if time_lim <= soft_lim:
            raise ValueError(
                "autoparse_run_company_time_limit_seconds must be greater than "
                "autoparse_run_company_soft_time_limit_seconds"
            )
        lock_ttl = self.autoparse_run_company_lock_ttl_seconds
        renew_iv = self.autoparse_run_company_lock_renew_interval_seconds
        if lock_ttl < renew_iv * 2:
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
        if self.cover_letter_pregen_time_limit <= self.cover_letter_pregen_soft_time_limit:
            raise ValueError(
                "cover_letter_pregen_time_limit must be greater than "
                "cover_letter_pregen_soft_time_limit"
            )
        if (
            self.autorespond_apply_pump_time_limit
            <= self.autorespond_apply_pump_soft_time_limit
        ):
            raise ValueError(
                "autorespond_apply_pump_time_limit must be greater than "
                "autorespond_apply_pump_soft_time_limit"
            )
        if (
            self.autorespond_apply_pump_chain_grace_seconds
            >= self.autorespond_apply_pump_soft_time_limit
        ):
            raise ValueError(
                "autorespond_apply_pump_chain_grace_seconds must be less than "
                "autorespond_apply_pump_soft_time_limit"
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
