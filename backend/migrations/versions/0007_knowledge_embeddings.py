"""Add explicit embedding builds and versioned chunk vectors."""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR

revision = "0007_knowledge_embeddings"
down_revision = "0006_knowledge_corpus"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_knowledge_chunk_checksum",
        "knowledge_chunks",
        ["citation_id", "content_sha256"],
        unique=True,
    )
    op.create_table(
        "embedding_builds",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("purpose", sa.String(12), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(250), nullable=False),
        sa.Column("model", sa.String(250), nullable=False),
        sa.Column("model_revision", sa.String(250)),
        sa.Column("location", sa.String(250)),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("query_encoding", sa.String(250), nullable=False),
        sa.Column("document_encoding", sa.String(250), nullable=False),
        sa.Column("preprocessing", sa.String(250), nullable=False),
        sa.Column("normalization", sa.String(250), nullable=False),
        sa.CheckConstraint("dimension = 384 AND generation > 0", name="ck_embedding_build_format"),
        sa.CheckConstraint("purpose IN ('production', 'test')", name="ck_embedding_build_purpose"),
        sa.CheckConstraint(
            "(provider = 'synthetic') = (purpose = 'test')",
            name="ck_embedding_synthetic_isolation",
        ),
    )
    op.create_table(
        "knowledge_chunk_vectors",
        sa.Column("build_id", sa.String(64), primary_key=True),
        sa.Column("citation_id", sa.String(200), primary_key=True),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("embedding", VECTOR(384).with_variant(sa.JSON(), "sqlite"), nullable=False),
        sa.ForeignKeyConstraint(["build_id"], ["embedding_builds.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["citation_id", "content_sha256"],
            ["knowledge_chunks.citation_id", "knowledge_chunks.content_sha256"],
            ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table("knowledge_chunk_vectors")
    op.drop_table("embedding_builds")
    op.drop_index("uq_knowledge_chunk_checksum", table_name="knowledge_chunks")
