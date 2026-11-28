"""Add versioned sources and conceptual knowledge chunks."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_knowledge_corpus"
down_revision = "0005_resolved_bs_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    document = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "knowledge_sources",
        sa.Column("source_id", sa.String(80), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("supersedes_version", sa.Integer()),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("collection", sa.String(12), nullable=False),
        sa.Column("rights_status", sa.String(24), nullable=False),
        sa.Column("bibliography", document, nullable=False),
        sa.Column("rights", document, nullable=False),
        sa.Column("artifact_sha256", sa.String(64), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("publication_review", sa.Text()),
        sa.ForeignKeyConstraint(
            ["source_id", "supersedes_version"],
            ["knowledge_sources.source_id", "knowledge_sources.version"],
        ),
        sa.CheckConstraint("version > 0", name="ck_knowledge_source_version"),
        sa.CheckConstraint("tier IN (2, 3)", name="ck_knowledge_source_tier"),
        sa.CheckConstraint("collection IN ('production', 'test')", name="ck_knowledge_collection"),
        sa.CheckConstraint(
            "rights_status IN ('public_domain_mark', 'licensed', 'project_owned', "
            "'unresolved', 'excluded')",
            name="ck_knowledge_rights",
        ),
        sa.CheckConstraint(
            "(version = 1 AND supersedes_version IS NULL) OR "
            "(version > 1 AND supersedes_version IS NOT NULL AND supersedes_version = version - 1)",
            name="ck_knowledge_source_supersedes",
        ),
        sa.CheckConstraint(
            "NOT enabled OR (collection = 'production' AND "
            "rights_status IN ('public_domain_mark', 'licensed', 'project_owned') "
            "AND publication_review IS NOT NULL)",
            name="ck_knowledge_source_publication",
        ),
    )
    op.create_index(
        "uq_knowledge_enabled_source",
        "knowledge_sources",
        ["source_id"],
        unique=True,
        postgresql_where=sa.text("enabled"),
        sqlite_where=sa.text("enabled"),
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("citation_id", sa.String(200), primary_key=True),
        sa.Column("source_id", sa.String(80), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("chunk_key", sa.String(80), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(35), nullable=False),
        sa.Column("topic", sa.String(24), nullable=False),
        sa.Column("tradition", sa.String(100), nullable=False),
        sa.Column("locator", document, nullable=False),
        sa.Column("applicability", document, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("editorial_status", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("editorial_review", sa.Text()),
        sa.UniqueConstraint(
            "source_id", "source_version", "chunk_key", name="uq_knowledge_chunk_key"
        ),
        sa.ForeignKeyConstraint(
            ["source_id", "source_version"],
            ["knowledge_sources.source_id", "knowledge_sources.version"],
        ),
        sa.CheckConstraint(
            "source_version > 0 AND revision > 0", name="ck_knowledge_chunk_version"
        ),
        sa.CheckConstraint(
            "editorial_status IN ('pending', 'approved', 'rejected') AND "
            "(editorial_status <> 'approved' OR editorial_review IS NOT NULL)",
            name="ck_knowledge_chunk_review",
        ),
    )
    op.create_index(
        "ix_knowledge_chunks_topic_source",
        "knowledge_chunks",
        ["topic", "source_id", "source_version"],
    )


def downgrade() -> None:
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_sources")
