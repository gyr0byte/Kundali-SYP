"""Metadata-first exact vector ranking with an explicit keyword fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import Select, and_, case
from sqlalchemy.orm import Session

from app.ai.embeddings import (
    EmbeddingError,
    EmbeddingProvider,
    EmbeddingQuery,
    Vector,
    normalize_vector,
)
from app.ai.vector_store import load_build
from app.db.models.embedding import KnowledgeChunkVector
from app.db.models.knowledge import KnowledgeChunk, KnowledgeSource
from app.knowledge.provenance import sha256
from app.knowledge.retrieval import Match, Search, match_candidate, retrieve, search_statement

FallbackReason = Literal["build_unavailable", "provider_unavailable", "vectors_unavailable"]


@dataclass(frozen=True)
class RetrievalResult:
    matches: tuple[Match, ...]
    mode: Literal["semantic", "keyword"]
    fallback_reason: FallbackReason | None = None


def vector_candidates(
    statement: Select[KnowledgeChunk, KnowledgeSource],
    build_id: str,
) -> Select[KnowledgeChunk, KnowledgeSource]:
    return statement.join(
        KnowledgeChunkVector,
        and_(
            KnowledgeChunkVector.citation_id == KnowledgeChunk.citation_id,
            KnowledgeChunkVector.content_sha256 == KnowledgeChunk.content_sha256,
            KnowledgeChunkVector.build_id == build_id,
        ),
    )


def order_by_cosine(
    statement: Select[KnowledgeChunk, KnowledgeSource],
    vector: Vector,
) -> Select[KnowledgeChunk, KnowledgeSource]:
    """Order already-filtered rows with the native exact pgvector distance."""
    distance = KnowledgeChunkVector.embedding.cosine_distance(list(vector))
    tier_bonus = case((KnowledgeSource.tier == 2, 0.01), else_=0.0)
    return statement.where(distance.between(0.0, 2.0)).order_by(
        distance - tier_bonus,
        KnowledgeSource.tier,
        KnowledgeChunk.citation_id.collate("C"),
    )


def _semantic_match(chunk: KnowledgeChunk, source: KnowledgeSource, search: Search) -> Match | None:
    match = match_candidate(chunk, source, search)
    if (
        match is None
        or "third_party_processing" not in match.rights.permitted_uses
        or sha256(chunk.content.encode("utf-8")) != chunk.content_sha256
    ):
        return None
    return match


def retrieve_semantic(
    session: Session,
    search: Search,
    intent: EmbeddingQuery,
    *,
    build_id: str,
    provider: EmbeddingProvider | None,
) -> RetrievalResult:
    """Serve only production rows from one requested build and provider configuration."""
    if {target.topic for target in intent.targets} != set(search.topics):
        raise ValueError("Semantic intent must match the requested topics")

    def fallback(reason: FallbackReason) -> RetrievalResult:
        return RetrievalResult(retrieve(session, search), "keyword", reason)

    if provider is None:
        return fallback("provider_unavailable")
    if load_build(session, build_id, provider.config, purpose="production") is None:
        return fallback("build_unavailable")
    if session.get_bind().dialect.name != "postgresql":
        return fallback("vectors_unavailable")
    eligible = search_statement(search)
    candidate_ids = []
    for chunk, source in session.execute(eligible.execution_options(populate_existing=True)):
        if _semantic_match(chunk, source, search) is not None:
            candidate_ids.append(chunk.citation_id)
    if not candidate_ids:
        return RetrievalResult((), "semantic")
    candidates = vector_candidates(
        eligible.where(KnowledgeChunk.citation_id.in_(candidate_ids)),
        build_id,
    )
    if session.execute(candidates.limit(1)).first() is None:
        return fallback("vectors_unavailable")
    try:
        # The provider receives only the allowlisted intent. Search and facts stay local.
        query_vector = normalize_vector(provider.embed_query(intent))
    except EmbeddingError:
        return fallback("provider_unavailable")

    matches = []
    # Reapply SQL eligibility to ranking and refresh ORM state for the final typed-fact check.
    ranked = order_by_cosine(candidates, query_vector).execution_options(populate_existing=True)
    for chunk, source in session.execute(ranked):
        if (match := _semantic_match(chunk, source, search)) is not None:
            matches.append(match)
            if len(matches) == search.limit:
                break
    return (
        RetrievalResult(tuple(matches), "semantic") if matches else fallback("vectors_unavailable")
    )
