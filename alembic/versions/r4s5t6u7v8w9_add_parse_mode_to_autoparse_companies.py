"""add parse mode fields to autoparse_companies

Revision ID: r4s5t6u7v8w9
Revises: a0b1c2d3e4f5
Create Date: 2026-04-10 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "r4s5t6u7v8w9"
down_revision: str | None = "a0b1c2d3e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "autoparse_companies",
        sa.Column("parse_mode", sa.String(length=16), nullable=False, server_default="api"),
    )
    op.add_column(
        "autoparse_companies",
        sa.Column("parse_hh_linked_account_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_autoparse_companies_parse_hh_linked_account",
        "autoparse_companies",
        "hh_linked_accounts",
        ["parse_hh_linked_account_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_autoparse_companies_parse_hh_linked_account",
        "autoparse_companies",
        type_="foreignkey",
    )
    op.drop_column("autoparse_companies", "parse_hh_linked_account_id")
    op.drop_column("autoparse_companies", "parse_mode")
