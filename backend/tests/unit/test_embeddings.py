"""Offline provider, storage and semantic pipeline contracts."""

import json
import math
from importlib import import_module
from unittest.mock import MagicMock

import httpx
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import MetaData, create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.embeddings import (
    DIMENSION,
    EmbeddingQuery,
    EmbeddingUnavailable,
    InvalidEmbedding,
    SyntheticEmbeddingProvider,
    normalize_vector,
)
from app.ai.gemini_embeddings import VertexGeminiEmbeddings
from app.ai.retrieval import retrieve_semantic
from app.ai.vector_store import (
    BuildCompatibilityError,
    IneligibleDocument,
    build_identity,
    embed_chunk,
    load_build,
    register_build,
)
from app.db.models.embedding import EmbeddingBuild, KnowledgeChunkVector
from app.db.models.knowledge import KnowledgeChunk, KnowledgeSource
from app.knowledge.ingestion import import_manifest, parse_manifest
from app.knowledge.provenance import canonical_bytes
from app.knowledge.retrieval import PlacementEvidence, Search, retrieve, search_statement
from tests.knowledge_fixtures import payload

INTENT = EmbeddingQuery.model_validate(
    {
        "targets": [{"topic": "planet_in_house", "planet": "Moon", "house": 5}],
    }
)
VECTOR = (1.0,) + (0.0,) * (DIMENSION - 1)


@pytest.mark.parametrize(
    "bad",
    [
        (),
        (0.0,) * DIMENSION,
        (float("nan"),) + VECTOR[1:],
        (float("inf"),) + VECTOR[1:],
        (True,) + VECTOR[1:],
        ("1",) + VECTOR[1:],
    ],
)
def test_invalid_vectors(bad):
    with pytest.raises(InvalidEmbedding):
        normalize_vector(bad)


def test_stable_synthetic_encoding_and_normalization():
    provider = SyntheticEmbeddingProvider()
    assert provider.embed_query(INTENT) == provider.embed_query(INTENT)
    assert provider.embed_query(INTENT) != provider.embed_document(INTENT.encode())
    assert math.hypot(*provider.embed_query(INTENT)) == pytest.approx(1)
    assert math.hypot(*normalize_vector((1.7e308,) * DIMENSION)) == pytest.approx(1)


@pytest.mark.parametrize(
    "extra",
    [
        {"query": "private question"},
        {"birth_time": "12:00"},
        {"snapshot_id": "id"},
        {"account_id": "id"},
        {"instant": "2026-01-01T12:00:00Z"},
    ],
)
def test_structured_intent_rejects_private_fields(extra):
    with pytest.raises(ValidationError):
        EmbeddingQuery.model_validate({"targets": [INTENT.targets[0].model_dump() | extra]})


def test_vertex_transport_has_distinct_tasks_and_no_truncation():
    requests = []

    def handle(request):
        data = json.loads(request.content)
        requests.append(data)
        assert request.url.host == "us-central1-aiplatform.googleapis.com"
        assert request.url.path.endswith("/publishers/google/models/gemini-embedding-001:predict")
        assert request.headers["Authorization"] == "Bearer fixture-token"
        assert "x-goog-api-key" not in request.headers
        assert request.extensions["timeout"] == {"connect": 2, "read": 4, "write": 4, "pool": 4}
        return httpx.Response(
            200,
            json={
                "predictions": [
                    {
                        "embeddings": {
                            "values": [2.0, *VECTOR[1:]],
                            "statistics": {"truncated": False},
                        }
                    }
                ],
            },
        )

    provider = VertexGeminiEmbeddings(
        "example-project",
        "us-central1",
        lambda: "fixture-token",
        transport=httpx.MockTransport(handle),
    )
    assert provider.embed_query(INTENT) == VECTOR
    assert provider.embed_document("Authorized synthetic document") == VECTOR
    assert requests == [
        {
            "instances": [{"content": content, "task_type": task}],
            "parameters": {"outputDimensionality": 384, "autoTruncate": False},
        }
        for content, task in (
            (INTENT.encode(), "RETRIEVAL_QUERY"),
            ("Authorized synthetic document", "RETRIEVAL_DOCUMENT"),
        )
    ]


@pytest.mark.parametrize(
    ("failure", "attempts", "error"),
    [
        ("timeout", 2, EmbeddingUnavailable),
        (429, 2, EmbeddingUnavailable),
        (403, 1, EmbeddingUnavailable),
        (302, 1, EmbeddingUnavailable),
        ("truncated", 1, InvalidEmbedding),
    ],
)
def test_vertex_failures_are_bounded_and_sanitized(failure, attempts, error):
    seen = []

    def handle(request):
        seen.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("sensitive diagnostics", request=request)
        if failure == "truncated":
            return httpx.Response(
                200,
                json={
                    "predictions": [
                        {
                            "embeddings": {"values": VECTOR, "statistics": {"truncated": True}},
                        }
                    ]
                },
            )
        return httpx.Response(
            failure, text="sensitive diagnostics", headers={"Location": "https://example.invalid/"}
        )

    provider = VertexGeminiEmbeddings(
        "example-project",
        "us-central1",
        lambda: "fixture-token",
        transport=httpx.MockTransport(handle),
    )
    with pytest.raises(error) as caught:
        provider.embed_query(INTENT)
    assert len(seen) == attempts
    assert "sensitive" not in str(caught.value)
    assert "fixture-token" not in str(caught.value)


def test_build_identity_compatibility_and_idempotent_writes(db_session: Session):
    provider = SyntheticEmbeddingProvider()
    build_id = register_build(db_session, provider.config, purpose="test", generation=1)
    assert register_build(db_session, provider.config, purpose="test", generation=1) == build_id
    second = register_build(db_session, provider.config, purpose="test", generation=2)
    assert second != build_id
    with pytest.raises(BuildCompatibilityError):
        register_build(db_session, provider.config, purpose="production", generation=1)
    different = provider.config.model_copy(update={"query_encoding": "other"})
    with pytest.raises(BuildCompatibilityError):
        load_build(db_session, build_id, different, purpose="test")
    db_session.rollback()
    manifest = parse_manifest(canonical_bytes(payload("test-embeddings", "test")))
    import_manifest(db_session, manifest, allow_test=True)
    citation_id = "test-embeddings@1/moon-fifth@1"
    assert embed_chunk(db_session, build_id, provider, citation_id, purpose="test")
    assert not embed_chunk(db_session, build_id, provider, citation_id, purpose="test")
    vector = db_session.get(KnowledgeChunkVector, (build_id, citation_id))
    assert vector is not None
    assert math.hypot(*vector.embedding) == pytest.approx(1)
    assert vector.content_sha256 == db_session.get(KnowledgeChunk, citation_id).content_sha256
    db_session.rollback()
    with pytest.raises(IntegrityError), db_session.begin():
        db_session.add(
            KnowledgeChunkVector(
                build_id=second,
                citation_id=citation_id,
                content_sha256="0" * 64,
                embedding=list(VECTOR),
            )
        )
    with db_session.begin():
        db_session.get(KnowledgeChunk, citation_id).content = "tampered text"
    with pytest.raises(IneligibleDocument, match="checksum"):
        embed_chunk(db_session, build_id, provider, citation_id, purpose="test")


def test_production_embedding_checks_status_collection_and_hosted_rights(db_session):
    provider = MagicMock()
    provider.config = VertexGeminiEmbeddings("example-project", "us-central1", lambda: "").config
    build_id = register_build(db_session, provider.config, purpose="production", generation=1)
    import_manifest(db_session, parse_manifest(canonical_bytes(payload())))
    import_manifest(
        db_session,
        parse_manifest(canonical_bytes(payload("test-source", "test"))),
        allow_test=True,
    )
    key = "fixture-corpus@1/moon-fifth@1"
    with pytest.raises(IneligibleDocument):
        embed_chunk(db_session, build_id, provider, key)
    with pytest.raises(IneligibleDocument):
        embed_chunk(db_session, build_id, provider, "test-source@1/moon-fifth@1")
    with db_session.begin():
        source = db_session.get(KnowledgeSource, ("fixture-corpus", 1))
        source.enabled = True
        source.publication_review = "isolated synthetic test"
    with pytest.raises(IneligibleDocument):  # Still pending.
        embed_chunk(db_session, build_id, provider, key)
    with db_session.begin():
        chunk = db_session.get(KnowledgeChunk, key)
        chunk.editorial_status = "approved"
        chunk.editorial_review = "isolated synthetic test"
    with pytest.raises(IneligibleDocument, match="hosted"):
        embed_chunk(db_session, build_id, provider, key)
    assert not provider.embed_document.called
    with db_session.begin():
        source = db_session.get(KnowledgeSource, ("fixture-corpus", 1))
        source.enabled = False
        source.rights_status = "excluded"
    with pytest.raises(IneligibleDocument):
        embed_chunk(db_session, build_id, provider, key)
    assert not provider.embed_document.called


def test_semantic_path_without_lexical_overlap_and_with_local_filtering(db_session):
    data = payload()
    data["source"]["rights"]["permitted_uses"].append("third_party_processing")
    import_manifest(db_session, parse_manifest(canonical_bytes(data)))
    with db_session.begin():
        source = db_session.get(KnowledgeSource, ("fixture-corpus", 1))
        source.enabled = True
        source.publication_review = "isolated synthetic test"
        for chunk in db_session.scalars(select(KnowledgeChunk)):
            chunk.editorial_review = "isolated synthetic test"
            chunk.editorial_status = "approved"
    search = Search(
        query="private phrase with zero lexical overlap",
        topics=("planet_in_house",),
        languages=("en",),
        placements=(PlacementEvidence(planet="Moon", house=5, certainty="approximate"),),
    )
    assert retrieve(db_session, search) == ()
    eligible = db_session.execute(search_statement(search)).one()
    config = VertexGeminiEmbeddings("example-project", "us-central1", lambda: "").config
    provider = MagicMock()
    provider.config = config
    provider.embed_query.return_value = VECTOR
    session = MagicMock(spec=Session)
    session.get_bind.return_value.dialect.name = "postgresql"
    build_id = build_identity(config, "production", 1)
    session.get.return_value = EmbeddingBuild(
        id=build_id,
        generation=1,
        purpose="production",
        **config.model_dump(),
    )
    session.execute.side_effect = [[eligible], MagicMock(first=lambda: eligible), [eligible]]
    result = retrieve_semantic(session, search, INTENT, build_id=build_id, provider=provider)
    assert result.mode == "semantic" and result.matches[0].conditional
    provider.embed_query.assert_called_once_with(INTENT)
    statement = session.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    assert "<=>" in str(statement) and "knowledge_sources.enabled IS true" in str(statement)
    assert statement.params["build_id_1"] == build_id
    assert "private phrase" not in str(statement.params)
    # Without matching facts, do not even call the provider.
    provider.reset_mock()
    session.execute.side_effect = [[eligible]]
    empty = retrieve_semantic(
        session,
        search.model_copy(update={"placements": ()}),
        INTENT,
        build_id=build_id,
        provider=provider,
    )
    assert empty.mode == "semantic" and empty.matches == ()
    assert not provider.embed_query.called
    session.execute.side_effect = [[eligible], MagicMock(first=lambda: None), [eligible]]
    lexical_search = search.model_copy(update={"query": "Moon"})
    missing = retrieve_semantic(
        session,
        lexical_search,
        INTENT,
        build_id=build_id,
        provider=provider,
    )
    assert missing.fallback_reason == "vectors_unavailable" and missing.mode == "keyword"
    assert missing.matches[0].citation_id == result.matches[0].citation_id
    assert not provider.embed_query.called
    session.execute.side_effect = [[eligible], MagicMock(first=lambda: eligible), [eligible]]
    provider.embed_query.side_effect = EmbeddingUnavailable("temporarily unavailable")
    unavailable = retrieve_semantic(
        session,
        lexical_search,
        INTENT,
        build_id=build_id,
        provider=provider,
    )
    assert unavailable.mode == "keyword" and unavailable.fallback_reason == "provider_unavailable"
    assert unavailable.matches == missing.matches
    fallback = retrieve_semantic(db_session, search, INTENT, build_id=build_id, provider=None)
    assert fallback.mode == "keyword" and fallback.fallback_reason == "provider_unavailable"


def test_embedding_migration_matches_orm_offline():
    engine = create_engine("sqlite://")
    corpus = import_module("migrations.versions.0006_knowledge_corpus")
    vectors = import_module("migrations.versions.0007_knowledge_embeddings")
    with engine.begin() as connection:
        context = MigrationContext.configure(connection, opts={"compare_server_default": True})
        with Operations.context(context):
            corpus.upgrade()
            vectors.upgrade()
            schema = MetaData()
            for model in (KnowledgeSource, KnowledgeChunk, EmbeddingBuild, KnowledgeChunkVector):
                model.__table__.to_metadata(schema)
            assert compare_metadata(context, schema) == []
            vectors.downgrade()
