"""remove include_reacted_in_feed and replay existing feed history

Revision ID: t6u7v8w9x0y1
Revises: s5t6u7v8w9x0
Create Date: 2026-04-10 18:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "t6u7v8w9x0y1"
down_revision: str | None = "s5t6u7v8w9x0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE autoparse_companies "
            "SET last_delivered_at = '1970-01-01 00:00:00'"
        )
    )
    op.drop_column("autoparse_companies", "include_reacted_in_feed")


def downgrade() -> None:
    op.add_column(
        "autoparse_companies",
        sa.Column(
            "include_reacted_in_feed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
