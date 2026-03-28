"""Load app_settings rows into the runtime ``settings`` object (bot + Celery workers)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.bot.modules.admin.keyboards import MANAGED_SETTINGS
from src.config import sync_setting_to_runtime
from src.repositories.app_settings import AppSettingRepository


async def load_managed_settings_to_runtime(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    """Apply all MANAGED_SETTINGS keys present in the DB to ``src.config.settings``.

    *session_factory*: when omitted, uses the process-wide engine (bot / one-off
    ``asyncio.run``). Celery ``run_async`` must pass the **per-task** factory from
    ``_create_task_session_factory()`` so asyncpg uses the same event loop as the task.
    """
    if session_factory is None:
        from src.db.engine import async_session_factory as session_factory

    keys = [item[0] for item in MANAGED_SETTINGS]
    async with session_factory() as session:
        repo = AppSettingRepository(session)
        by_key = await repo.get_values_for_keys(keys)
        for key in keys:
            val = by_key.get(key)
            if val is not None:
                sync_setting_to_runtime(key, val)
