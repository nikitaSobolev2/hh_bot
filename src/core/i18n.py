"""Internationalization built on fluent.runtime (no aiogram-i18n dependency)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from aiogram import BaseMiddleware, Dispatcher
from aiogram.types import TelegramObject
from fluent.runtime import FluentLocalization, FluentResourceLoader

from src.core.logging import get_logger

logger = get_logger(__name__)

LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"
_DEFAULT_LOCALE = "ru"
_SUPPORTED_LOCALES = ("ru", "en")

_loader = FluentResourceLoader(str(LOCALES_DIR / "{locale}" / "LC_MESSAGES"))

_localizations: dict[str, FluentLocalization] = {}


def _get_localization(locale: str) -> FluentLocalization:
    if locale not in _localizations:
        _localizations[locale] = FluentLocalization(
            locales=[locale, _DEFAULT_LOCALE],
            resource_ids=["messages.ftl"],
            resource_loader=_loader,
        )
    return _localizations[locale]


class I18nContext:
    """Minimal i18n context injected into handler data by the middleware."""

    def __init__(self, locale: str = _DEFAULT_LOCALE) -> None:
        self._locale = locale
        self._loc = _get_localization(locale)

    @property
    def locale(self) -> str:
        return self._locale

    def get(self, key: str, **kwargs: Any) -> str:
        result = self._loc.format_value(key, kwargs or None)
        return result or key


class I18nMiddleware(BaseMiddleware):
    """Reads ``data["locale"]`` and injects an ``I18nContext`` as ``data["i18n"]``."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        locale = data.get("locale", _DEFAULT_LOCALE)
        if locale not in _SUPPORTED_LOCALES:
            locale = _DEFAULT_LOCALE
        data["i18n"] = I18nContext(locale)
        return await handler(event, data)


def setup_i18n(dp: Dispatcher) -> None:
    """Register the i18n middleware on the dispatcher."""
    dp.update.middleware(I18nMiddleware())


def get_text(key: str, locale: str = _DEFAULT_LOCALE, **kwargs: Any) -> str:
    """Resolve a Fluent key outside the middleware context."""
    loc = _get_localization(locale)
    result = loc.format_value(key, kwargs or None)
    return result or key
