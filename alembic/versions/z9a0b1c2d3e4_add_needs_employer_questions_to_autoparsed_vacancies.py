"""add needs_employer_questions to autoparsed_vacancies

Revision ID: z9a0b1c2d3e4
Revises: x7y8z9a0b1c2
Create Date: 2026-03-24 23:30:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "z9a0b1c2d3e4"
down_revision: Union[str, None] = "x7y8z9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "autoparsed_vacancies",
        sa.Column("needs_employer_questions", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("autoparsed_vacancies", "needs_employer_questions")
