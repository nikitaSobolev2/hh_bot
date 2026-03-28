from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.app_settings import AppSetting
from src.repositories.base import BaseRepository


class AppSettingRepository(BaseRepository[AppSetting]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AppSetting)

    async def get_by_key(self, key: str) -> AppSetting | None:
        stmt = select(AppSetting).where(AppSetting.key == key)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_value(self, key: str, default: Any = None) -> Any:
        setting = await self.get_by_key(key)
        if setting is None or setting.value is None:
            return default
        return setting.value

    async def get_values_for_keys(self, keys: Sequence[str]) -> dict[str, Any]:
        """Return key → value for existing rows (one query). Values may be None."""
        if not keys:
            return {}
        stmt = select(AppSetting.key, AppSetting.value).where(AppSetting.key.in_(keys))
        result = await self._session.execute(stmt)
        return dict(result.all())

    async def set_value(
        self,
        key: str,
        value: Any,
        *,
        description: str = "",
        updated_by_id: int | None = None,
    ) -> AppSetting:
        setting = await self.get_by_key(key)
        if setting is None:
            return await self.create(
                key=key,
                value=value,
                description=description,
                updated_by_id=updated_by_id,
            )
        return await self.update(
            setting,
            value=value,
            updated_by_id=updated_by_id,
        )
