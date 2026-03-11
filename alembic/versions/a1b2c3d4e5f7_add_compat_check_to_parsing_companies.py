"""add compat check to parsing companies

Revision ID: a1b2c3d4e5f7
Revises: df15f0a4b4f0
Create Date: 2026-03-11 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f7"
down_revision: str = "df15f0a4b4f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "parsing_companies",
        sa.Column(
            "use_compatibility_check",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "parsing_companies",
        sa.Column("compatibility_threshold", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("parsing_companies", "compatibility_threshold")
    op.drop_column("parsing_companies", "use_compatibility_check")
