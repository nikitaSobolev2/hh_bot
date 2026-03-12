"""merge feature and interview heads

Revision ID: c0d1e2f3a4b5
Revises: a7b8c9d0e1f2, b1c2d3e4f5a6
Create Date: 2026-03-12 12:00:00.000000

"""

from collections.abc import Sequence

revision: str = "c0d1e2f3a4b5"
down_revision: tuple[str, str] = ("a7b8c9d0e1f2", "b1c2d3e4f5a6")
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
