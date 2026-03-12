"""add generation params to vacancy_summaries

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
Create Date: 2026-03-12 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: str = "c0d1e2f3a4b5"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("vacancy_summaries", sa.Column("excluded_industries", sa.Text(), nullable=True))
    op.add_column("vacancy_summaries", sa.Column("location", sa.Text(), nullable=True))
    op.add_column("vacancy_summaries", sa.Column("remote_preference", sa.Text(), nullable=True))
    op.add_column("vacancy_summaries", sa.Column("additional_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("vacancy_summaries", "additional_notes")
    op.drop_column("vacancy_summaries", "remote_preference")
    op.drop_column("vacancy_summaries", "location")
    op.drop_column("vacancy_summaries", "excluded_industries")
