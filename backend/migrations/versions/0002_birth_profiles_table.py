"""Add birth_profiles table with encrypted birth identity fields.

Revision ID: 0002_birth_profiles_table
Revises: 0001_initial_auth_tables
Create Date: 2026-11-25 19:35:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic.
revision: str = "0002_birth_profiles_table"
down_revision: str | None = "0001_initial_auth_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the encrypted birth_profiles table."""
    op.create_table(
        "birth_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("label_enc", sa.LargeBinary(), nullable=False),
        sa.Column(
            "input_calendar",
            sa.Enum("AD", "BS", name="input_calendar", native_enum=False, create_constraint=False),
            nullable=False,
        ),
        sa.Column("entered_date_enc", sa.LargeBinary(), nullable=False),
        sa.Column("date_ad_enc", sa.LargeBinary(), nullable=True),
        sa.Column(
            "time_certainty",
            sa.Enum(
                "exact",
                "approximate",
                "unknown",
                name="time_certainty",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("time_local_enc", sa.LargeBinary(), nullable=True),
        sa.Column("place_name_enc", sa.LargeBinary(), nullable=False),
        sa.Column("latitude_enc", sa.LargeBinary(), nullable=False),
        sa.Column("longitude_enc", sa.LargeBinary(), nullable=False),
        sa.Column("timezone_enc", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "input_calendar IN ('AD', 'BS')",
            name="check_birth_profile_input_calendar",
        ),
        sa.CheckConstraint(
            "time_certainty IN ('exact', 'approximate', 'unknown')",
            name="check_birth_profile_time_certainty",
        ),
        sa.CheckConstraint(
            "(time_certainty = 'unknown' AND time_local_enc IS NULL) "
            "OR (time_certainty IN ('exact', 'approximate') AND time_local_enc IS NOT NULL)",
            name="check_birth_profile_time_local_certainty",
        ),
        sa.CheckConstraint(
            "(input_calendar = 'BS' AND date_ad_enc IS NULL) "
            "OR (input_calendar = 'AD' AND date_ad_enc IS NOT NULL)",
            name="check_birth_profile_calendar_date_ad",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_birth_profiles_owner_id"),
        "birth_profiles",
        ["owner_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the birth_profiles table and its owner index."""
    op.drop_index(op.f("ix_birth_profiles_owner_id"), table_name="birth_profiles")
    op.drop_table("birth_profiles")
