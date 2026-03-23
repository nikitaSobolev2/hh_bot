"""add browser_storage_enc to hh_linked_accounts

Revision ID: u2v3w4x5y6z7
Revises: q1r2s3t4u5v6
Create Date: 2026-03-24 14:00:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "u2v3w4x5y6z7"
down_revision: Union[str, None] = "q1r2s3t4u5v6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "hh_linked_accounts",
        sa.Column("browser_storage_enc", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "hh_linked_accounts",
        sa.Column("browser_storage_updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("hh_linked_accounts", "browser_storage_updated_at")
    op.drop_column("hh_linked_accounts", "browser_storage_enc")
