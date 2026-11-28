"""Versioned, shared editorial material. No chart or account inputs."""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PortableJSON


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_id", "supersedes_version"],
            ["knowledge_sources.source_id", "knowledge_sources.version"],
        ),
        CheckConstraint("version > 0", name="ck_knowledge_source_version"),
        CheckConstraint("tier IN (2, 3)", name="ck_knowledge_source_tier"),
        CheckConstraint("collection IN ('production', 'test')", name="ck_knowledge_collection"),
        CheckConstraint(
            "rights_status IN ('public_domain_mark', 'licensed', 'project_owned', "
            "'unresolved', 'excluded')",
            name="ck_knowledge_rights",
        ),
        CheckConstraint(
            "(version = 1 AND supersedes_version IS NULL) OR "
            "(version > 1 AND supersedes_version IS NOT NULL AND supersedes_version = version - 1)",
            name="ck_knowledge_source_supersedes",
        ),
        CheckConstraint(
            "NOT enabled OR (collection = 'production' AND "
            "rights_status IN ('public_domain_mark', 'licensed', 'project_owned') "
            "AND publication_review IS NOT NULL)",
            name="ck_knowledge_source_publication",
        ),
        Index(
            "uq_knowledge_enabled_source",
            "source_id",
            unique=True,
            postgresql_where=text("enabled"),
            sqlite_where=text("enabled"),
        ),
    )

    source_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    supersedes_version: Mapped[int | None]
    tier: Mapped[int]
    collection: Mapped[str] = mapped_column(String(12))
    rights_status: Mapped[str] = mapped_column(String(24))
    bibliography: Mapped[dict[str, object]] = mapped_column(PortableJSON)
    rights: Mapped[dict[str, object]] = mapped_column(PortableJSON)
    artifact_sha256: Mapped[str] = mapped_column(String(64))
    content_sha256: Mapped[str] = mapped_column(String(64))
    manifest_sha256: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    publication_review: Mapped[str | None] = mapped_column(Text)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("source_id", "source_version", "chunk_key", name="uq_knowledge_chunk_key"),
        ForeignKeyConstraint(
            ["source_id", "source_version"],
            ["knowledge_sources.source_id", "knowledge_sources.version"],
        ),
        CheckConstraint("source_version > 0 AND revision > 0", name="ck_knowledge_chunk_version"),
        CheckConstraint(
            "editorial_status IN ('pending', 'approved', 'rejected') AND "
            "(editorial_status <> 'approved' OR editorial_review IS NOT NULL)",
            name="ck_knowledge_chunk_review",
        ),
        Index("ix_knowledge_chunks_topic_source", "topic", "source_id", "source_version"),
        Index("uq_knowledge_chunk_checksum", "citation_id", "content_sha256", unique=True),
    )

    citation_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(80))
    source_version: Mapped[int]
    chunk_key: Mapped[str] = mapped_column(String(80))
    revision: Mapped[int]
    language: Mapped[str] = mapped_column(String(35))
    topic: Mapped[str] = mapped_column(String(24))
    tradition: Mapped[str] = mapped_column(String(100))
    locator: Mapped[dict[str, object]] = mapped_column(PortableJSON)
    applicability: Mapped[dict[str, object]] = mapped_column(PortableJSON)
    content: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64))
    editorial_status: Mapped[str] = mapped_column(String(12), server_default=text("'pending'"))
    editorial_review: Mapped[str | None] = mapped_column(Text)
