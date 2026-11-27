"""Enable pgvector on PostgreSQL without taking ownership of an existing extension."""

from alembic import op

revision = "0003_enable_pgvector"
down_revision = "0002_birth_profiles_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Retain vector because another consumer may rely on it."""
