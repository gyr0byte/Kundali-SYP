"""Allow encrypted Gregorian dates for resolved or legacy pending BS profiles."""

from alembic import op

revision = "0005_resolved_bs_profiles"
down_revision = "0004_chart_snapshots"
branch_labels = None
depends_on = None

_CONSTRAINT = "check_birth_profile_calendar_date_ad"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "birth_profiles", type_="check")
    op.create_check_constraint(
        _CONSTRAINT, "birth_profiles", "input_calendar = 'BS' OR date_ad_enc IS NOT NULL"
    )


def downgrade() -> None:
    # Intentionally refuse downgrade while resolved BS rows exist, rather than erase dates.
    op.drop_constraint(_CONSTRAINT, "birth_profiles", type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        "birth_profiles",
        "(input_calendar = 'BS' AND date_ad_enc IS NULL) "
        "OR (input_calendar = 'AD' AND date_ad_enc IS NOT NULL)",
    )
