"""add cover_letter_vacancies table

Revision ID: p0q1r2s3t4u5
Revises: o9p0q1r2s3t4
Create Date: 2026-03-18 12:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "p0q1r2s3t4u5"
down_revision: Union[str, None] = "o9p0q1r2s3t4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cover_letter_vacancies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("hh_vacancy_id", sa.String(50), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("company_name", sa.String(500), nullable=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("raw_skills", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "hh_vacancy_id", name="uq_cover_letter_user_vacancy"),
    )
    op.create_index(
        "ix_cover_letter_vacancies_hh_vacancy_id",
        "cover_letter_vacancies",
        ["hh_vacancy_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_cover_letter_vacancies_hh_vacancy_id", "cover_letter_vacancies")
    op.drop_table("cover_letter_vacancies")
