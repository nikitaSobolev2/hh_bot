"""add parse_hh_linked_account_id to parsing_companies

Revision ID: y1z2a3b4c5d6
Revises: t6u7v8w9x0y1
Create Date: 2026-05-22 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "y1z2a3b4c5d6"
down_revision: str | None = "t6u7v8w9x0y1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "parsing_companies",
        sa.Column("parse_hh_linked_account_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_parsing_companies_parse_hh_linked_account",
        "parsing_companies",
        "hh_linked_accounts",
        ["parse_hh_linked_account_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_parsing_companies_parse_hh_linked_account",
        "parsing_companies",
        type_="foreignkey",
    )
    op.drop_column("parsing_companies", "parse_hh_linked_account_id")
