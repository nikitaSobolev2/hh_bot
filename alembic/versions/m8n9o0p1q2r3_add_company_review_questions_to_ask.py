"""add company_review and questions_to_ask to interviews

Revision ID: m8n9o0p1q2r3
Revises: l7m8n9o0p1q2
Create Date: 2026-03-16 00:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "m8n9o0p1q2r3"
down_revision: Union[str, None] = "l7m8n9o0p1q2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "interviews",
        sa.Column("company_review", sa.Text(), nullable=True),
    )
    op.add_column(
        "interviews",
        sa.Column("questions_to_ask", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("interviews", "questions_to_ask")
    op.drop_column("interviews", "company_review")
