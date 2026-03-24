"""add resume_list_cache to hh_linked_accounts

Revision ID: w3x4y5z6a7b8
Revises: u2v3w4x5y6z7
Create Date: 2026-03-24 16:00:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "w3x4y5z6a7b8"
down_revision: Union[str, None] = "u2v3w4x5y6z7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "hh_linked_accounts",
        sa.Column("resume_list_cache", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "hh_linked_accounts",
        sa.Column("resume_list_cached_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("hh_linked_accounts", "resume_list_cached_at")
    op.drop_column("hh_linked_accounts", "resume_list_cache")
