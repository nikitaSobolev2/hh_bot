"""merge heads

Revision ID: df15f0a4b4f0
Revises: f9e2d1c0b7a3, c1d2e3f4a5b6
Create Date: 2026-03-10 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "df15f0a4b4f0"
down_revision: tuple[str, str] = ("f9e2d1c0b7a3", "c1d2e3f4a5b6")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
