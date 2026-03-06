from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.user import User


class Role(Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    users: Mapped[list[User]] = relationship(back_populates="role")
    permissions: Mapped[list[RolePermission]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def has_permission(self, permission: str) -> bool:
        return any(p.permission == permission for p in self.permissions)

    def __repr__(self) -> str:
        return f"<Role id={self.id} name={self.name!r}>"


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission", name="uq_role_permission"),)

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    permission: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="")

    role: Mapped[Role] = relationship(back_populates="permissions")

    def __repr__(self) -> str:
        return f"<RolePermission role_id={self.role_id} permission={self.permission!r}>"
