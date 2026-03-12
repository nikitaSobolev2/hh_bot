"""merge we_ai_drafts and title_period heads

Revision ID: g1h2i3j4k5l6
Revises: f0a1b2c3d4e5, f6a7b8c9d0e1
Create Date: 2026-03-12 23:00:00.000000

"""

from collections.abc import Sequence

revision: str = "g1h2i3j4k5l6"
down_revision: tuple[str, str] = ("f0a1b2c3d4e5", "f6a7b8c9d0e1")
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
