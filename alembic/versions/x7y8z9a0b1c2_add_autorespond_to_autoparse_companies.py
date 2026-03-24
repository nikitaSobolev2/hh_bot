"""add autorespond columns to autoparse_companies

Revision ID: x7y8z9a0b1c2
Revises: w3x4y5z6a7b8
Create Date: 2026-03-24 20:00:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "x7y8z9a0b1c2"
down_revision: Union[str, None] = "w3x4y5z6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "autoparse_companies",
        sa.Column("autorespond_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "autoparse_companies",
        sa.Column("autorespond_min_compat", sa.Integer(), nullable=False, server_default="50"),
    )
    op.add_column(
        "autoparse_companies",
        sa.Column(
            "autorespond_keyword_mode",
            sa.String(length=32),
            nullable=False,
            server_default="title_and_keywords",
        ),
    )
    op.add_column(
        "autoparse_companies",
        sa.Column("autorespond_max_per_run", sa.Integer(), nullable=False, server_default="20"),
    )
    op.add_column(
        "autoparse_companies",
        sa.Column("autorespond_resume_id", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "autoparse_companies",
        sa.Column("autorespond_hh_linked_account_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_autoparse_companies_autorespond_hh_linked_account",
        "autoparse_companies",
        "hh_linked_accounts",
        ["autorespond_hh_linked_account_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_autoparse_companies_autorespond_hh_linked_account",
        "autoparse_companies",
        type_="foreignkey",
    )
    op.drop_column("autoparse_companies", "autorespond_hh_linked_account_id")
    op.drop_column("autoparse_companies", "autorespond_resume_id")
    op.drop_column("autoparse_companies", "autorespond_max_per_run")
    op.drop_column("autoparse_companies", "autorespond_keyword_mode")
    op.drop_column("autoparse_companies", "autorespond_min_compat")
    op.drop_column("autoparse_companies", "autorespond_enabled")
