"""HeadHunter Playwright login assist availability."""

from src.config import settings


def login_assist_available() -> bool:
    return bool(
        settings.hh_login_assist_enabled
        and settings.hh_ui_apply_enabled
        and settings.hh_token_encryption_key
    )
