"""add_raw_api_data_to_vacancies

Revision ID: d81285d05a37
Revises: h2i3j4k5l6m7
Create Date: 2026-03-15 01:03:09.217820

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d81285d05a37"
down_revision: Union[str, None] = "h2i3j4k5l6m7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "parsed_vacancies",
        sa.Column("raw_api_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "autoparsed_vacancies",
        sa.Column("raw_api_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("parsed_vacancies", "raw_api_data")
    op.drop_column("autoparsed_vacancies", "raw_api_data")
