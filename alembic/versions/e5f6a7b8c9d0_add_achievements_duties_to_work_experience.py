"""add achievements and duties to user_work_experiences

Revision ID: e5f6a7b8c9d0
Revises: d1e2f3a4b5c6
Create Date: 2026-03-12 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str = "d1e2f3a4b5c6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_work_experiences", sa.Column("achievements", sa.Text(), nullable=True))
    op.add_column("user_work_experiences", sa.Column("duties", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_work_experiences", "duties")
    op.drop_column("user_work_experiences", "achievements")
