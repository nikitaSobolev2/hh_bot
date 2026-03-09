"""add ai_analysis to autoparsed_vacancies

Revision ID: f9e2d1c0b7a3
Revises: b3c7f1a2e894
Create Date: 2026-03-10 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f9e2d1c0b7a3"
down_revision: str | None = "b3c7f1a2e894"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "autoparsed_vacancies",
        sa.Column("ai_summary", sa.Text(), nullable=True),
    )
    op.add_column(
        "autoparsed_vacancies",
        sa.Column("ai_stack", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("autoparsed_vacancies", "ai_stack")
    op.drop_column("autoparsed_vacancies", "ai_summary")
