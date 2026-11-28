"""Immutable embedding builds and chunk vectors."""

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import JSON, CheckConstraint, ForeignKey, ForeignKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EmbeddingBuild(Base):
    __tablename__ = "embedding_builds"
    __table_args__ = (
        CheckConstraint("dimension = 384 AND generation > 0", name="ck_embedding_build_format"),
        CheckConstraint("purpose IN ('production', 'test')", name="ck_embedding_build_purpose"),
        CheckConstraint(
            "(provider = 'synthetic') = (purpose = 'test')",
            name="ck_embedding_synthetic_isolation",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    purpose: Mapped[str] = mapped_column(String(12))
    generation: Mapped[int]
    provider: Mapped[str] = mapped_column(String(250))
    model: Mapped[str] = mapped_column(String(250))
    model_revision: Mapped[str | None] = mapped_column(String(250))
    location: Mapped[str | None] = mapped_column(String(250))
    dimension: Mapped[int]
    query_encoding: Mapped[str] = mapped_column(String(250))
    document_encoding: Mapped[str] = mapped_column(String(250))
    preprocessing: Mapped[str] = mapped_column(String(250))
    normalization: Mapped[str] = mapped_column(String(250))


class KnowledgeChunkVector(Base):
    __tablename__ = "knowledge_chunk_vectors"
    __table_args__ = (
        ForeignKeyConstraint(
            ["citation_id", "content_sha256"],
            ["knowledge_chunks.citation_id", "knowledge_chunks.content_sha256"],
            ondelete="CASCADE",
        ),
    )

    build_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("embedding_builds.id", ondelete="CASCADE"), primary_key=True
    )
    citation_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    content_sha256: Mapped[str] = mapped_column(String(64))
    embedding: Mapped[list[float]] = mapped_column(VECTOR(384).with_variant(JSON(), "sqlite"))
