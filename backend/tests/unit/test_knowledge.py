"""Offline knowledge tests. Publication stand-ins exist only in in-memory SQLite."""

import json
from importlib import import_module
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import MetaData, create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.knowledge import KnowledgeChunk, KnowledgeSource
from app.knowledge.ingestion import ManifestConflict, import_manifest, parse_manifest
from app.knowledge.provenance import canonical_bytes
from app.knowledge.retrieval import Search, resolve_citation, retrieve
from tests.knowledge_fixtures import payload

ROOT = Path(__file__).resolve().parents[3]


def test_database_migration_matches_orm():
    engine = create_engine("sqlite://")
    migration = import_module("migrations.versions.0006_knowledge_corpus")
    with engine.begin() as connection:
        context = MigrationContext.configure(connection, opts={"compare_server_default": True})
        with Operations.context(context):
            migration.upgrade()
            schema = MetaData()
            KnowledgeSource.__table__.to_metadata(schema)
            chunks = KnowledgeChunk.__table__.to_metadata(schema)
            # This check targets revision 0006. Revision 0007 adds the checksum index.
            chunks.indexes = {
                index for index in chunks.indexes if index.name != "uq_knowledge_chunk_checksum"
            }
            assert compare_metadata(context, schema) == []
            migration.downgrade()


def test_candidate_manifests(db_session: Session):
    files = sorted((ROOT / "docs/architecture/knowledge-candidates").glob("*.json"))
    assert len(files) == 2
    count = 0
    for path in files:
        manifest = parse_manifest(path.read_bytes())
        assert manifest.source.tier == 2
        assert manifest.source.language == "en"
        assert manifest.source.rights.status == "public_domain_mark"
        assert all(chunk.applicability.topic not in ("pada", "dasha") for chunk in manifest.chunks)
        assert import_manifest(db_session, manifest).inserted
        count += len(manifest.chunks)
    assert 24 <= count <= 40
    assert all(
        not source.enabled and source.publication_review is None
        for source in db_session.scalars(select(KnowledgeSource))
    )
    assert all(
        chunk.editorial_status == "pending" and chunk.editorial_review is None
        for chunk in db_session.scalars(select(KnowledgeChunk))
    )


@pytest.mark.parametrize(
    "field", ["enabled", "tier", "title", "rights", "checksum", "applicability", "schema_version"]
)
def test_invalid_manifests(field):
    data = payload()
    source = data["source"]
    if field == "schema_version":
        data["manifest_schema_version"] = True
    elif field == "enabled":
        source["enabled"] = True
    elif field == "tier":
        source["tier"] = 1
    elif field == "title":
        source["title"] = ""
    elif field == "rights":
        source["rights"]["permitted_uses"] = ["reproduce"]
    elif field == "checksum":
        data["chunks"][0]["text"] += " modified"
    else:
        data["chunks"][1]["applicability"]["house"] = True
    with pytest.raises(ValidationError):
        parse_manifest(canonical_bytes(data))


def test_idempotency_release_history_and_isolation(db_session: Session):
    data = payload()
    first = parse_manifest(canonical_bytes(data), artifact=b"artifact")
    assert import_manifest(db_session, first).inserted
    data["chunks"].reverse()
    data["source"]["rights"]["permitted_uses"].reverse()
    assert not import_manifest(db_session, parse_manifest(canonical_bytes(data))).inserted
    with pytest.raises(ManifestConflict):
        import_manifest(db_session, parse_manifest(canonical_bytes(payload(text="conflict"))))
    with pytest.raises(ManifestConflict):
        import_manifest(
            db_session, parse_manifest(canonical_bytes(payload(version=2, text="changed")))
        )
    with pytest.raises(ValueError, match="checksum"):
        parse_manifest(canonical_bytes(data), artifact=b"other")
    query = Search(query="Moon", topics=("planet_general",), languages=("en",))
    assert retrieve(db_session, query) == ()
    db_session.rollback()
    test_manifest = parse_manifest(canonical_bytes(payload("test-fixture", "test")))
    with pytest.raises(ValueError, match="test-mode"):
        import_manifest(db_session, test_manifest)
    assert import_manifest(db_session, test_manifest, allow_test=True).inserted
    with pytest.raises(IntegrityError), db_session.begin():
        test_source = db_session.get(KnowledgeSource, ("test-fixture", 1))
        test_source.enabled = True
        test_source.publication_review = "fixture review"
    _publish_fixture(db_session, enabled=True, approve=False)
    assert retrieve(db_session, query) == ()
    db_session.rollback()
    _publish_fixture(db_session)
    (original,) = retrieve(db_session, query)
    db_session.rollback()
    revised = parse_manifest(canonical_bytes(payload(version=2, revision=2, text="revised")))
    assert import_manifest(db_session, revised).inserted
    with db_session.begin():
        db_session.get(KnowledgeSource, ("fixture-corpus", 1)).enabled = False
    assert retrieve(db_session, query) == ()
    assert resolve_citation(db_session, original.citation_id) is not None
    db_session.rollback()
    with db_session.begin():
        db_session.get(KnowledgeSource, ("fixture-corpus", 1)).rights_status = "excluded"
    assert resolve_citation(db_session, original.citation_id) is None
    assert len(list(db_session.scalars(select(KnowledgeChunk)))) == 9


def _publish_fixture(session: Session, *, enabled=True, approve=True):
    with session.begin():
        source = session.get(KnowledgeSource, ("fixture-corpus", 1))
        source.enabled = enabled
        source.publication_review = "isolated test assertion"
        if approve:
            for chunk in session.scalars(select(KnowledgeChunk)):
                chunk.editorial_status = "approved"
                chunk.editorial_review = "isolated test assertion"


def test_failure_after_source_insert_rolls_back_entire_release(db_session: Session):
    manifest = parse_manifest(canonical_bytes(payload()))

    def fail_chunk_flush(session, context, instances):
        if any(isinstance(row, KnowledgeChunk) for row in session.new):
            raise RuntimeError("forced chunk failure")

    event.listen(db_session, "before_flush", fail_chunk_flush)
    try:
        with pytest.raises(RuntimeError, match="forced chunk failure"):
            import_manifest(db_session, manifest)
    finally:
        event.remove(db_session, "before_flush", fail_chunk_flush)
    assert db_session.get(KnowledgeSource, ("fixture-corpus", 1)) is None
    assert list(db_session.scalars(select(KnowledgeChunk))) == []


def test_retrieval_labels_and_conditionality(db_session: Session):
    import_manifest(db_session, parse_manifest(canonical_bytes(payload())))
    _publish_fixture(db_session)
    labels = ROOT / "backend/tests/fixtures/knowledge-retrieval-eval.json"
    for case in json.loads(labels.read_text(encoding="utf-8")):
        expected = case.pop("keys")
        request = Search.model_validate({"languages": ["en"], **case})
        assert [
            item.citation_id.split("/")[-1].split("@")[0] for item in retrieve(db_session, request)
        ] == expected
    approx = Search.model_validate(
        {
            "query": "Moon",
            "topics": ["planet_in_house"],
            "languages": ["en"],
            "placements": [{"planet": "Moon", "house": 5, "certainty": "approximate"}],
        }
    )
    assert retrieve(db_session, approx)[0].conditional
    instant = {
        "snapshot_id": "00000000-0000-0000-0000-000000000001",
        "instant": "2026-01-01T12:00:00.000001Z",
    }
    search = {
        "query": "Venus",
        "topics": ["dasha"],
        "languages": ["en"],
        "evaluation": instant,
        "dashas": [
            {
                "evaluation": instant,
                "method": "vimshottari-v1",
                "level": "AD",
                "lord": "Venus",
                "parent_lord": "Sun",
                "certainty": "approximate",
            }
        ],
    }
    assert retrieve(db_session, Search.model_validate(search))[0].conditional
    search["evaluation"] = {**instant, "instant": "2026-01-01T12:00:00.000002Z"}
    assert retrieve(db_session, Search.model_validate(search)) == ()
