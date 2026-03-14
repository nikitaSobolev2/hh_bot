"""add hh_employers, hh_areas and normalized vacancy columns

Revision ID: i3j4k5l6m7n8
Revises: h2i3j4k5l6m7
Create Date: 2026-03-15 12:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "i3j4k5l6m7n8"
down_revision: Union[str, None] = "h2i3j4k5l6m7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "hh_employers",
        sa.Column("hh_employer_id", sa.String(50), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("alternate_url", sa.Text(), nullable=True),
        sa.Column("logo_urls", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("vacancies_url", sa.Text(), nullable=True),
        sa.Column("accredited_it_employer", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("trusted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_identified_by_esia", sa.Boolean(), nullable=True),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_hh_employers_hh_employer_id", "hh_employers", ["hh_employer_id"], unique=True
    )

    op.create_table(
        "hh_areas",
        sa.Column("hh_area_id", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hh_areas_hh_area_id", "hh_areas", ["hh_area_id"], unique=True)

    # Drop raw_api_data if it exists (from previously applied d81285d05a37)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    for table in ("parsed_vacancies", "autoparsed_vacancies"):
        columns = [c["name"] for c in inspector.get_columns(table)]
        if "raw_api_data" in columns:
            op.drop_column(table, "raw_api_data")

    # Add new columns to parsed_vacancies
    op.add_column(
        "parsed_vacancies",
        sa.Column("employer_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "parsed_vacancies",
        sa.Column("area_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_parsed_vacancies_employer_id",
        "parsed_vacancies",
        "hh_employers",
        ["employer_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_parsed_vacancies_area_id",
        "parsed_vacancies",
        "hh_areas",
        ["area_id"],
        ["id"],
        ondelete="SET NULL",
    )

    _add_vacancy_columns("parsed_vacancies")

    # Add new columns to autoparsed_vacancies
    op.add_column(
        "autoparsed_vacancies",
        sa.Column("employer_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "autoparsed_vacancies",
        sa.Column("area_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_autoparsed_vacancies_employer_id",
        "autoparsed_vacancies",
        "hh_employers",
        ["employer_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_autoparsed_vacancies_area_id",
        "autoparsed_vacancies",
        "hh_areas",
        ["area_id"],
        ["id"],
        ondelete="SET NULL",
    )

    _add_vacancy_columns("autoparsed_vacancies")


def _add_vacancy_columns(table: str) -> None:
    op.add_column(table, sa.Column("snippet_requirement", sa.Text(), nullable=True))
    op.add_column(table, sa.Column("snippet_responsibility", sa.Text(), nullable=True))
    op.add_column(table, sa.Column("experience_id", sa.String(50), nullable=True))
    op.add_column(table, sa.Column("experience_name", sa.String(200), nullable=True))
    op.add_column(table, sa.Column("schedule_id", sa.String(50), nullable=True))
    op.add_column(table, sa.Column("schedule_name", sa.String(200), nullable=True))
    op.add_column(table, sa.Column("employment_id", sa.String(50), nullable=True))
    op.add_column(table, sa.Column("employment_name", sa.String(200), nullable=True))
    op.add_column(table, sa.Column("employment_form_id", sa.String(50), nullable=True))
    op.add_column(table, sa.Column("employment_form_name", sa.String(200), nullable=True))
    op.add_column(table, sa.Column("salary_from", sa.Integer(), nullable=True))
    op.add_column(table, sa.Column("salary_to", sa.Integer(), nullable=True))
    op.add_column(table, sa.Column("salary_currency", sa.String(10), nullable=True))
    op.add_column(table, sa.Column("salary_gross", sa.Boolean(), nullable=True))
    op.add_column(table, sa.Column("address_raw", sa.Text(), nullable=True))
    op.add_column(table, sa.Column("address_city", sa.String(200), nullable=True))
    op.add_column(table, sa.Column("address_street", sa.String(500), nullable=True))
    op.add_column(table, sa.Column("address_building", sa.String(100), nullable=True))
    op.add_column(table, sa.Column("address_lat", sa.Float(), nullable=True))
    op.add_column(table, sa.Column("address_lng", sa.Float(), nullable=True))
    op.add_column(table, sa.Column("metro_stations", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column(table, sa.Column("vacancy_type_id", sa.String(50), nullable=True))
    op.add_column(table, sa.Column("published_at", sa.DateTime(), nullable=True))
    op.add_column(table, sa.Column("work_format", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column(table, sa.Column("professional_roles", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    for table in ("parsed_vacancies", "autoparsed_vacancies"):
        op.drop_column(table, "professional_roles")
        op.drop_column(table, "work_format")
        op.drop_column(table, "published_at")
        op.drop_column(table, "vacancy_type_id")
        op.drop_column(table, "metro_stations")
        op.drop_column(table, "address_lng")
        op.drop_column(table, "address_lat")
        op.drop_column(table, "address_building")
        op.drop_column(table, "address_street")
        op.drop_column(table, "address_city")
        op.drop_column(table, "address_raw")
        op.drop_column(table, "salary_gross")
        op.drop_column(table, "salary_currency")
        op.drop_column(table, "salary_to")
        op.drop_column(table, "salary_from")
        op.drop_column(table, "employment_form_name")
        op.drop_column(table, "employment_form_id")
        op.drop_column(table, "employment_name")
        op.drop_column(table, "employment_id")
        op.drop_column(table, "schedule_name")
        op.drop_column(table, "schedule_id")
        op.drop_column(table, "experience_name")
        op.drop_column(table, "experience_id")
        op.drop_column(table, "snippet_responsibility")
        op.drop_column(table, "snippet_requirement")

    op.drop_constraint("fk_autoparsed_vacancies_area_id", "autoparsed_vacancies", type_="foreignkey")
    op.drop_constraint("fk_autoparsed_vacancies_employer_id", "autoparsed_vacancies", type_="foreignkey")
    op.drop_column("autoparsed_vacancies", "area_id")
    op.drop_column("autoparsed_vacancies", "employer_id")

    op.drop_constraint("fk_parsed_vacancies_area_id", "parsed_vacancies", type_="foreignkey")
    op.drop_constraint("fk_parsed_vacancies_employer_id", "parsed_vacancies", type_="foreignkey")
    op.drop_column("parsed_vacancies", "area_id")
    op.drop_column("parsed_vacancies", "employer_id")

    op.drop_index("ix_hh_areas_hh_area_id", table_name="hh_areas")
    op.drop_table("hh_areas")
    op.drop_index("ix_hh_employers_hh_employer_id", table_name="hh_employers")
    op.drop_table("hh_employers")
