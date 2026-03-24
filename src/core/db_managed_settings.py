"""Load app_settings rows into the runtime ``settings`` object (bot + Celery workers)."""

from __future__ import annotations

from src.bot.modules.admin.keyboards import MANAGED_SETTINGS
from src.config import sync_setting_to_runtime
from src.db.engine import async_session_factory
from src.repositories.app_settings import AppSettingRepository


async def load_managed_settings_to_runtime() -> None:
    """Apply all MANAGED_SETTINGS keys present in the DB to ``src.config.settings``."""
    async with async_session_factory() as session:
        repo = AppSettingRepository(session)
        for item in MANAGED_SETTINGS:
            key = item[0]
            val = await repo.get_value(key)
            if val is not None:
                sync_setting_to_runtime(key, val)
