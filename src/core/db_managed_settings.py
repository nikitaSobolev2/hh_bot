"""Load app_settings rows into the runtime ``settings`` object (bot + Celery workers)."""

from __future__ import annotations

from src.bot.modules.admin.keyboards import MANAGED_SETTINGS
from src.config import sync_setting_to_runtime
from src.db.engine import async_session_factory
from src.repositories.app_settings import AppSettingRepository


async def load_managed_settings_to_runtime() -> None:
    """Apply all MANAGED_SETTINGS keys present in the DB to ``src.config.settings``."""
    keys = [item[0] for item in MANAGED_SETTINGS]
    async with async_session_factory() as session:
        repo = AppSettingRepository(session)
        by_key = await repo.get_values_for_keys(keys)
        for key in keys:
            val = by_key.get(key)
            if val is not None:
                sync_setting_to_runtime(key, val)
