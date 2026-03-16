"""add tasks_interview_qa table

Revision ID: o9p0q1r2s3t4
Revises: n9o0p1q2r3s4
Create Date: 2026-03-16 12:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "o9p0q1r2s3t4"
down_revision: Union[str, None] = "n9o0p1q2r3s4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tasks_interview_qa",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["id"], ["celery_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            INSERT INTO tasks_interview_qa (id)
            SELECT id FROM celery_tasks WHERE task_type = 'interview_qa'
            """
        )
    )


def downgrade() -> None:
    op.drop_table("tasks_interview_qa")
