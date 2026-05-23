"""add integrated_duties columns and tasks_integrate_duties table

Revision ID: z2a3b4c5d6e7
Revises: y1z2a3b4c5d6
Create Date: 2026-05-23 12:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "z2a3b4c5d6e7"
down_revision: Union[str, None] = "y1z2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "aggregated_results",
        sa.Column("integrated_duties", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "aggregated_results",
        sa.Column("integrated_duties_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "tasks_integrate_duties",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("parsing_company_id", sa.Integer(), nullable=False),
        sa.Column("generated_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["id"], ["celery_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["parsing_company_id"],
            ["parsing_companies.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("tasks_integrate_duties")
    op.drop_column("aggregated_results", "integrated_duties_at")
    op.drop_column("aggregated_results", "integrated_duties")
