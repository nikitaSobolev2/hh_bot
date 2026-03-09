"""add last_delivered_at to autoparse_companies

Revision ID: b3c7f1a2e894
Revises: 4ae5988f2049
Create Date: 2026-03-09 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3c7f1a2e894"
down_revision: str | None = "4ae5988f2049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "autoparse_companies",
        sa.Column("last_delivered_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("autoparse_companies", "last_delivered_at")
