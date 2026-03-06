"""Seed initial roles and permissions into the database."""

import asyncio

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.config import settings
from src.core.logging import setup_logging, get_logger
from src.db.engine import async_session_factory
from src.models.role import Role, RolePermission

logger = get_logger(__name__)

ROLES = {
    "admin": [
        ("admin.panel.access", "Access admin panel"),
        ("admin.users.view", "View user list"),
        ("admin.users.ban", "Ban/unban users"),
        ("admin.users.balance", "Adjust user balance"),
        ("admin.users.message", "Send message to user"),
        ("admin.settings.view", "View app settings"),
        ("admin.settings.edit", "Edit app settings"),
        ("admin.tasks.manage", "Enable/disable Celery tasks"),
        ("parsing.create", "Create parsing companies"),
    ],
    "user": [
        ("parsing.create", "Create parsing companies"),
    ],
}


async def seed() -> None:
    setup_logging()
    async with async_session_factory() as session:
        for role_name, permissions in ROLES.items():
            stmt = (
                select(Role)
                .where(Role.name == role_name)
                .options(selectinload(Role.permissions))
            )
            result = await session.execute(stmt)
            role = result.scalar_one_or_none()

            if role is None:
                role = Role(name=role_name)
                session.add(role)
                await session.flush()
                logger.info("Created role", role=role_name)
                existing: set[str] = set()
            else:
                existing = {p.permission for p in role.permissions}
            for perm_name, perm_desc in permissions:
                if perm_name not in existing:
                    perm = RolePermission(
                        role_id=role.id, permission=perm_name, description=perm_desc,
                    )
                    session.add(perm)
                    logger.info("Added permission", role=role_name, permission=perm_name)

        await session.commit()
    logger.info("Seed completed")


if __name__ == "__main__":
    asyncio.run(seed())
