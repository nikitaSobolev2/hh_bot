"""add hh_linked_accounts, hh_application_attempts, VacancyFeedSession.hh_linked_account_id

Revision ID: q1r2s3t4u5v6
Revises: p0q1r2s3t4u5
Create Date: 2026-03-24 12:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "q1r2s3t4u5v6"
down_revision: Union[str, None] = "p0q1r2s3t4u5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "hh_linked_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("hh_user_id", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("access_token_enc", sa.LargeBinary(), nullable=False),
        sa.Column("refresh_token_enc", sa.LargeBinary(), nullable=False),
        sa.Column("access_expires_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "hh_user_id", name="uq_hh_linked_user_hh_user"),
    )
    op.create_index("ix_hh_linked_accounts_user_id", "hh_linked_accounts", ["user_id"])

    op.create_table(
        "hh_application_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("hh_linked_account_id", sa.Integer(), nullable=True),
        sa.Column("autoparsed_vacancy_id", sa.Integer(), nullable=True),
        sa.Column("hh_vacancy_id", sa.String(length=50), nullable=False),
        sa.Column("resume_id", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("api_negotiation_id", sa.String(length=80), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("response_excerpt", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["hh_linked_account_id"],
            ["hh_linked_accounts.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["autoparsed_vacancy_id"],
            ["autoparsed_vacancies.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hh_application_attempts_user_id", "hh_application_attempts", ["user_id"])

    op.add_column(
        "vacancy_feed_sessions",
        sa.Column("hh_linked_account_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_vacancy_feed_sessions_hh_linked_account",
        "vacancy_feed_sessions",
        "hh_linked_accounts",
        ["hh_linked_account_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_vacancy_feed_sessions_hh_linked_account",
        "vacancy_feed_sessions",
        type_="foreignkey",
    )
    op.drop_column("vacancy_feed_sessions", "hh_linked_account_id")
    op.drop_table("hh_application_attempts")
    op.drop_table("hh_linked_accounts")
