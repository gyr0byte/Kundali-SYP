"""Persist encrypted chart snapshots, scoped to birth profile revisions."""

import sqlalchemy as sa
from alembic import op

revision = "0004_chart_snapshots"
down_revision = "0003_enable_pgvector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "birth_profiles", sa.Column("revision", sa.Integer(), server_default="1", nullable=False)
    )
    op.create_table(
        "chart_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("birth_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("profile_revision", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("fingerprint_key", sa.String(64), nullable=False),
        sa.Column("payload_enc", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "profile_id",
            "profile_revision",
            "schema_version",
            "fingerprint_key",
            name="uq_chart_snapshots_result",
        ),
    )


def downgrade() -> None:
    op.drop_table("chart_snapshots")
    op.drop_column("birth_profiles", "revision")
