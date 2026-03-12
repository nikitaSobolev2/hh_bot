"""add title and period to user_work_experiences

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-03-12 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str = "e5f6a7b8c9d0"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_work_experiences", sa.Column("title", sa.String(255), nullable=True))
    op.add_column("user_work_experiences", sa.Column("period", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("user_work_experiences", "period")
    op.drop_column("user_work_experiences", "title")
