"""Opt-in, transactional embedding builds over eligible knowledge."""

from __future__ import annotations

from typing import Literal

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.ai.embeddings import EmbeddingConfig, EmbeddingProvider, normalize_vector
from app.db.models.embedding import EmbeddingBuild, KnowledgeChunkVector
from app.db.models.knowledge import KnowledgeChunk, KnowledgeSource
from app.knowledge.provenance import canonical_bytes, sha256
from app.knowledge.retrieval import eligible_statement, validated_citation

BuildPurpose = Literal["production", "test"]


class BuildCompatibilityError(ValueError):
    """The selected build and encoding configuration do not agree."""


class IneligibleDocument(ValueError):
    """A document cannot be processed under the selected build."""


def build_identity(config: EmbeddingConfig, purpose: BuildPurpose, generation: int) -> str:
    if type(generation) is not int or not 1 <= generation <= 2147483647:
        raise ValueError("Invalid embedding build generation")
    if purpose not in ("production", "test") or (purpose == "test") != (
        config.provider == "synthetic"
    ):
        raise BuildCompatibilityError("Synthetic providers and test builds must be isolated")
    return sha256(canonical_bytes(["embedding-build-v1", purpose, generation, config.model_dump()]))


def register_build(
    session: Session,
    config: EmbeddingConfig,
    *,
    purpose: BuildPurpose,
    generation: int,
) -> str:
    """Register an explicit generation with an idempotent atomic insert."""
    build_id = build_identity(config, purpose, generation)
    insert = postgres_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    with session.begin():
        session.execute(
            insert(EmbeddingBuild)
            .values(
                id=build_id,
                purpose=purpose,
                generation=generation,
                **config.model_dump(),
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
        if load_build(session, build_id, config, purpose=purpose) is None:
            raise BuildCompatibilityError("Embedding build could not be registered")
    return build_id


def load_build(
    session: Session,
    build_id: str,
    config: EmbeddingConfig,
    *,
    purpose: BuildPurpose,
) -> EmbeddingBuild | None:
    row = session.get(EmbeddingBuild, build_id)
    if row is None:
        return None
    try:
        stored = EmbeddingConfig.model_validate(row, from_attributes=True)
    except ValidationError:
        raise BuildCompatibilityError("Stored embedding build configuration is invalid") from None
    if (
        row.purpose != purpose
        or stored != config
        or build_identity(stored, purpose, row.generation) != build_id
    ):
        raise BuildCompatibilityError("Provider or collection does not match the selected build")
    return row


def embed_chunk(
    session: Session,
    build_id: str,
    provider: EmbeddingProvider,
    citation_id: str,
    *,
    purpose: BuildPurpose = "production",
) -> bool:
    """Encode one eligible document and insert its vector on a fresh writer session."""
    postgres = session.get_bind().dialect.name == "postgresql"
    insert = postgres_insert if postgres else sqlite_insert
    with session.begin():
        if load_build(session, build_id, provider.config, purpose=purpose) is None:
            raise BuildCompatibilityError("Selected embedding build does not exist")
        if purpose == "production":
            statement = eligible_statement(current=True)
        else:
            statement = (
                select(KnowledgeChunk, KnowledgeSource)
                .join(
                    KnowledgeSource,
                )
                .where(KnowledgeSource.collection == "test")
            )
        statement = statement.where(KnowledgeChunk.citation_id == citation_id)
        if postgres:
            # Keep the approved source and chunk unchanged through the provider dispatch/write.
            statement = statement.with_for_update(read=True, of=(KnowledgeSource, KnowledgeChunk))
        row = session.execute(statement).one_or_none()
        if row is None:
            raise IneligibleDocument("Chunk is outside the build's eligible collection")
        chunk, source = row
        if purpose == "production":
            citation = validated_citation(chunk, source)
            if citation is None or "third_party_processing" not in citation.rights.permitted_uses:
                raise IneligibleDocument("Chunk is not cleared for hosted embedding")
        checksum = sha256(chunk.content.encode("utf-8"))
        if checksum != chunk.content_sha256:
            raise IneligibleDocument("Chunk content checksum does not match")
        existing = session.get(KnowledgeChunkVector, (build_id, citation_id))
        if existing is not None:
            if existing.content_sha256 != checksum:
                raise IneligibleDocument("Stored embedding checksum does not match")
            return False
        vector = normalize_vector(provider.embed_document(chunk.content))
        inserted = session.scalar(
            insert(KnowledgeChunkVector)
            .values(
                build_id=build_id,
                citation_id=citation_id,
                content_sha256=checksum,
                embedding=list(vector),
            )
            .on_conflict_do_nothing(index_elements=["build_id", "citation_id"])
            .returning(KnowledgeChunkVector.citation_id)
        )
        return inserted is not None
