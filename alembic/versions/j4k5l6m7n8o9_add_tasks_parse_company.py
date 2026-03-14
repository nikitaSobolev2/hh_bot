"""add tasks_parse_company table

Revision ID: j4k5l6m7n8o9
Revises: i3j4k5l6m7n8
Create Date: 2026-03-15 14:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "j4k5l6m7n8o9"
down_revision: Union[str, None] = "i3j4k5l6m7n8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tasks_parse_company",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("parsing_company_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["id"], ["celery_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["parsing_company_id"], ["parsing_companies.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Backfill: insert rows for existing celery_tasks with task_type='parse_company'
    # idempotency_key format: "parse_company:{parsing_company_id}"
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            INSERT INTO tasks_parse_company (id, parsing_company_id)
            SELECT id, (split_part(idempotency_key, ':', 2))::integer
            FROM celery_tasks
            WHERE task_type = 'parse_company'
              AND idempotency_key LIKE 'parse_company:%'
              AND split_part(idempotency_key, ':', 2) ~ '^[0-9]+$'
            """
        )
    )


def downgrade() -> None:
    op.drop_table("tasks_parse_company")
