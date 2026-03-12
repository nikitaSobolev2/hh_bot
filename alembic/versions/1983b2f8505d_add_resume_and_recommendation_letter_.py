"""add_resume_and_recommendation_letter_tables

Revision ID: 1983b2f8505d
Revises: g1h2i3j4k5l6
Create Date: 2026-03-13 00:48:18.260773

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1983b2f8505d"
down_revision: Union[str, None] = "g1h2i3j4k5l6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resumes",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("job_title", sa.String(length=255), nullable=False),
        sa.Column("skill_level", sa.String(length=100), nullable=True),
        sa.Column("parsed_keywords", sa.JSON(), nullable=True),
        sa.Column("keyphrases_by_company", sa.JSON(), nullable=True),
        sa.Column("disabled_work_exp_ids", sa.JSON(), nullable=True),
        sa.Column("summary_id", sa.Integer(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["summary_id"], ["vacancy_summaries.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_resumes_user_id"), "resumes", ["user_id"], unique=False)

    op.create_table(
        "recommendation_letters",
        sa.Column("resume_id", sa.Integer(), nullable=False),
        sa.Column("work_experience_id", sa.Integer(), nullable=False),
        sa.Column("speaker_name", sa.String(length=255), nullable=False),
        sa.Column("speaker_position", sa.String(length=255), nullable=True),
        sa.Column("character", sa.String(length=100), nullable=False),
        sa.Column("focus_text", sa.Text(), nullable=True),
        sa.Column("generated_text", sa.Text(), nullable=True),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["work_experience_id"],
            ["user_work_experiences.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_recommendation_letters_resume_id"),
        "recommendation_letters",
        ["resume_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_recommendation_letters_resume_id"),
        table_name="recommendation_letters",
    )
    op.drop_table("recommendation_letters")
    op.drop_index(op.f("ix_resumes_user_id"), table_name="resumes")
    op.drop_table("resumes")
