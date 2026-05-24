"""add autorespond_cover_letter to autoparsed_vacancies

Revision ID: a1b2c3d4e5f8
Revises: z2a3b4c5d6e7
Create Date: 2026-05-24 14:00:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f8"
down_revision: Union[str, None] = "z2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "autoparsed_vacancies",
        sa.Column("autorespond_cover_letter", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("autoparsed_vacancies", "autorespond_cover_letter")
