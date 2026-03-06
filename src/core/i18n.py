"""Internationalization setup using aiogram-i18n with Fluent.

STATUS: Infrastructure is ready (Fluent .ftl files for ru/en, locale middleware,
FluentRuntimeCore). Handlers currently use hardcoded strings. To complete i18n,
handlers need to accept an ``i18n`` parameter and call ``i18n.gettext("key")``.
"""

from pathlib import Path

from aiogram_i18n import I18nMiddleware
from aiogram_i18n.cores.fluent_runtime_core import FluentRuntimeCore

from src.core.logging import get_logger

logger = get_logger(__name__)

LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"


class UserLocaleManager:
    """Resolves the locale for the current user from the DB user object."""

    async def get_locale(self, event_from_user=None, user=None, **kwargs) -> str:
        if user is not None:
            return getattr(user, "language_code", "ru") or "ru"
        if event_from_user is not None:
            return getattr(event_from_user, "language_code", "ru") or "ru"
        return "ru"


def create_i18n_middleware() -> I18nMiddleware:
    core = FluentRuntimeCore(
        path=str(LOCALES_DIR / "{locale}" / "LC_MESSAGES"),
        default_locale="ru",
    )
    return I18nMiddleware(
        core=core,
        locale_key="locale",
        middleware_key="i18n",
        default_locale="ru",
    )
