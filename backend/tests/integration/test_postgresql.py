"""Opt-in integration checks. Use a fresh, independently selected disposable database."""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from math import hypot
from pathlib import Path
from queue import Queue
from threading import Event
from time import monotonic
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation
from sqlalchemy import event, insert, inspect, select, text, update
from sqlalchemy.engine import URL, Connection, Engine, Row
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai import retrieval as semantic_retrieval
from app.ai.embeddings import DIMENSION, EmbeddingQuery, SyntheticEmbeddingProvider
from app.ai.retrieval import order_by_cosine, vector_candidates
from app.ai.vector_store import BuildCompatibilityError, embed_chunk, load_build, register_build
from app.api.schemas.profile import BirthProfileCreate, BirthProfileUpdate
from app.calc.facts import ChartSettings
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.mailer import ConsoleMailer
from app.core.permissions import UserRole
from app.core.security import hash_token
from app.db.base import Base
from app.db.connection import DatabaseConfigurationError, postgres_engine, postgres_url
from app.db.models import (
    AstrologerProfile,
    AstrologerStatus,
    AuditLog,
    BirthProfile,
    ChartSnapshot,
    InputCalendar,
    KnowledgeChunk,
    KnowledgeChunkVector,
    KnowledgeSource,
    RefreshToken,
    TimeCertainty,
    User,
)
from app.knowledge.ingestion import ManifestConflict, import_manifest, parse_manifest
from app.knowledge.provenance import canonical_bytes
from app.knowledge.retrieval import PlacementEvidence, Search, resolve_citation, retrieve
from app.services import auth_service, user_service
from app.services.account_locks import lock_administration, lock_user
from app.services.astrologer_service import approve_astrologer
from app.services.audit_service import log_action
from app.services.chart_service import (
    ChartProfileConflictError,
    calculate_profile_chart,
    get_chart_snapshot,
    persist_chart_snapshot,
)
from app.services.profile_service import create_profile, delete_profile, update_profile
from tests.knowledge_fixtures import payload

BACKEND = Path(__file__).resolve().parents[2]


def disposable_url(value: str, ca_file: str | None, expected: str | None) -> URL:
    url = postgres_url(value, ca_file)
    if (
        not expected
        or expected != f"{url.host}:{url.port}/{url.database}"
        or not (url.database or "").startswith("kundali_test_")
    ):
        raise DatabaseConfigurationError("Disposable PostgreSQL test target did not match.")
    return url


@pytest.mark.parametrize(
    ("name", "expected_name"),
    [("kundali_dev", "kundali_dev"), ("kundali_test_other", "kundali_test_probe")],
)
def test_disposable_guard_rejects_wrong_target(
    monkeypatch: pytest.MonkeyPatch, name: str, expected_name: str
) -> None:
    monkeypatch.delenv("PGSERVICE", raising=False)
    monkeypatch.delenv("PGHOSTADDR", raising=False)
    with pytest.raises(DatabaseConfigurationError, match="test target did not match"):
        disposable_url(
            f"postgresql://fixture:fixture@db.example/{name}",
            __file__,
            f"db.example:5432/{expected_name}",
        )


@pytest.fixture(scope="module")
def migrated_database() -> Iterator[MigratedDatabase]:
    if os.environ.get("KUNDALI_RUN_POSTGRES_TESTS") != "1":
        pytest.skip("Disposable PostgreSQL integration is opt-in.")

    engine = None
    try:
        url = disposable_url(
            os.environ.get("KUNDALI_TEST_DATABASE_URL", ""),
            os.environ.get("KUNDALI_DB_CA_FILE"),
            os.environ.get("KUNDALI_TEST_DATABASE_TARGET"),
        )
        engine = postgres_engine(url)
        with engine.begin() as connection:
            correct_target = connection.scalar(
                text(
                    "SELECT current_database() = :db AND current_user = :role "
                    "AND current_schema() = 'public'"
                ),
                {"db": url.database, "role": url.username},
            )
            existing = connection.scalar(
                text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE left(n.nspname, 3) <> 'pg_' AND n.nspname <> 'information_schema'
                      AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
                )
            """)
            )
            if not correct_target or existing:
                pytest.fail(
                    "Expected an empty disposable database and the intended role.", pytrace=False
                )

            cfg = Config(str(BACKEND / "alembic.ini"))
            cfg.set_main_option("script_location", str(BACKEND / "migrations"))
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "0004_chart_snapshots")
            legacy = _seed_legacy_profiles(connection)
            command.upgrade(cfg, "0006_knowledge_corpus")
            with Session(bind=connection) as session:
                manifest = parse_manifest(canonical_bytes(payload("test-legacy-knowledge", "test")))
                import_manifest(session, manifest, allow_test=True)
            knowledge_before = _legacy_knowledge(connection)
            command.upgrade(cfg, "head")
        yield MigratedDatabase(engine, legacy, knowledge_before)
    except Exception:
        pytest.fail(
            "Disposable PostgreSQL setup failed. Check the target and permissions privately.",
            pytrace=False,
        )
    finally:
        if engine is not None:
            engine.dispose()


@dataclass(frozen=True)
class LegacyProfiles:
    ad_id: uuid.UUID
    bs_id: uuid.UUID
    profiles: list[Row[Any]]
    snapshot: Row[Any]
    normalized_bs_date: bytes


@dataclass(frozen=True)
class MigratedDatabase:
    engine: Engine
    legacy: LegacyProfiles
    knowledge_before: tuple[list[Row[Any]], list[Row[Any]]]


def _legacy_knowledge(connection: Connection) -> tuple[list[Row[Any]], list[Row[Any]]]:
    source_id = "test-legacy-knowledge"
    return (
        list(
            connection.execute(
                select(KnowledgeSource.__table__).where(KnowledgeSource.source_id == source_id)
            )
        ),
        list(
            connection.execute(
                select(KnowledgeChunk.__table__)
                .where(KnowledgeChunk.source_id == source_id)
                .order_by(KnowledgeChunk.citation_id)
            )
        ),
    )


def _migration_profile_rows(
    connection: Connection, ad_id: uuid.UUID, bs_id: uuid.UUID
) -> list[Row[Any]]:
    return list(
        connection.execute(
            select(BirthProfile.__table__)
            .where(BirthProfile.id.in_((ad_id, bs_id)))
            .order_by(BirthProfile.id)
        )
    )


def _seed_legacy_profiles(connection: Connection) -> LegacyProfiles:
    owner_id, ad_id, bs_id = (uuid.uuid4() for _ in range(3))
    key = Fernet.generate_key()
    cipher = Fernet(key)
    connection.execute(
        insert(User).values(
            id=owner_id,
            email="migration-0005@example.com",
            password_hash="disabled-test-login",
            is_active=False,
        )
    )
    fields = {
        "owner_id": owner_id,
        "label_enc": cipher.encrypt(b"Synthetic migration profile"),
        "time_certainty": "exact",
        "time_local_enc": cipher.encrypt(b"12:00"),
        "place_name_enc": cipher.encrypt(b"Synthetic place"),
        "latitude_enc": cipher.encrypt(b"27.7"),
        "longitude_enc": cipher.encrypt(b"85.3"),
        "timezone_enc": cipher.encrypt(b"Asia/Kathmandu"),
    }
    connection.execute(
        insert(BirthProfile).values(
            **fields,
            id=ad_id,
            revision=3,
            input_calendar="AD",
            entered_date_enc=cipher.encrypt(b"2000-01-01"),
            date_ad_enc=cipher.encrypt(b"2000-01-01"),
        )
    )
    connection.execute(
        insert(BirthProfile).values(
            **fields,
            id=bs_id,
            revision=7,
            input_calendar="BS",
            entered_date_enc=cipher.encrypt(b"2072-01-12"),
            date_ad_enc=None,
        )
    )
    settings = Settings.model_construct(ENCRYPTION_KEY=key.decode("ascii"))
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        profile = session.get(BirthProfile, ad_id)
        assert profile is not None
        result = calculate_profile_chart(
            profile, owner_id=owner_id, calc_settings=ChartSettings(), app_settings=settings
        )
        snapshot_id = persist_chart_snapshot(
            session,
            result,
            profile_revision=profile.revision,
            owner_id=owner_id,
            app_settings=settings,
        )
    snapshot = connection.execute(
        select(ChartSnapshot.__table__).where(ChartSnapshot.id == snapshot_id)
    ).one()
    return LegacyProfiles(
        ad_id,
        bs_id,
        _migration_profile_rows(connection, ad_id, bs_id),
        snapshot,
        cipher.encrypt(b"2015-04-25"),
    )


@pytest.fixture(scope="module")
def migrated_engine(migrated_database: MigratedDatabase) -> Engine:
    return migrated_database.engine


@pytest.fixture
def db_session(migrated_engine: Engine) -> Iterator[Session]:
    # App services commit. Use the one-use migrated database instead of a rollback-only fixture.
    with Session(migrated_engine, expire_on_commit=False) as session:
        yield session


def test_migration_0005_preserves_legacy_profiles_and_snapshot(
    migrated_database: MigratedDatabase,
) -> None:
    legacy = migrated_database.legacy
    with migrated_database.engine.connect() as connection:
        assert _migration_profile_rows(connection, legacy.ad_id, legacy.bs_id) == legacy.profiles
        assert (
            connection.execute(
                select(ChartSnapshot.__table__).where(ChartSnapshot.id == legacy.snapshot.id)
            ).one()
            == legacy.snapshot
        )
        # The connection rolls these probes back so the module's data remains unchanged.
        assert (
            connection.scalar(
                update(BirthProfile)
                .where(BirthProfile.id == legacy.bs_id)
                .values(date_ad_enc=legacy.normalized_bs_date)
                .returning(BirthProfile.date_ad_enc)
            )
            == legacy.normalized_bs_date
        )
        for values, constraint in (
            ({"date_ad_enc": None}, "check_birth_profile_calendar_date_ad"),
            ({"input_calendar": "XX"}, "check_birth_profile_input_calendar"),
        ):
            with pytest.raises(IntegrityError) as error, connection.begin_nested():
                connection.execute(
                    update(BirthProfile).where(BirthProfile.id == legacy.ad_id).values(**values)
                )
            assert isinstance(error.value.orig, CheckViolation)
            assert error.value.orig.diag.constraint_name == constraint


def test_migrations_match_models_and_install_vector(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM public.alembic_version"))
            == "0007_knowledge_embeddings"
        )
        assert connection.scalar(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        )
        assert set(Base.metadata.tables) <= set(
            inspect(connection).get_table_names(schema="public")
        )
        migration = MigrationContext.configure(connection, opts={"compare_server_default": True})
        assert compare_metadata(migration, Base.metadata) == []


def test_postgres_pgvector_migration_preserves_corpus(migrated_database: MigratedDatabase) -> None:
    sources, chunks = migrated_database.knowledge_before
    assert len(sources) == 1 and len(chunks) == 3
    with migrated_database.engine.connect() as connection:
        assert _legacy_knowledge(connection) == migrated_database.knowledge_before
        assert (
            connection.scalar(
                text("""
            SELECT format_type(atttypid, atttypmod)
            FROM pg_attribute
            WHERE attrelid = 'public.knowledge_chunk_vectors'::regclass AND attname = 'embedding'
        """)
            )
            == "vector(384)"
        )


def test_postgres_pgvector_exact_ranking_in_isolated_test_build(db_session: Session) -> None:
    class KnownVectors(SyntheticEmbeddingProvider):
        def embed_document(self, text: str) -> tuple[float, ...]:
            return (
                (1.0, 0.0, *(0.0,) * (DIMENSION - 2))
                if "fifth" in text
                else (0.0, 1.0, *(0.0,) * (DIMENSION - 2))
            )

    provider = KnownVectors()
    build = register_build(db_session, provider.config, purpose="test", generation=701)
    other = register_build(db_session, provider.config, purpose="test", generation=702)
    import_manifest(
        db_session,
        parse_manifest(canonical_bytes(payload("test-pgvector-ranking", "test"))),
        allow_test=True,
    )
    prefix = "test-pgvector-ranking@1/"
    for key in ("moon-general", "moon-fifth", "venus-period"):
        assert embed_chunk(db_session, build, provider, prefix + key + "@1", purpose="test")
    assert not embed_chunk(db_session, build, provider, prefix + "moon-fifth@1", purpose="test")
    assert embed_chunk(db_session, other, provider, prefix + "moon-general@1", purpose="test")
    with pytest.raises(IntegrityError) as failure, db_session.begin():
        db_session.add(
            KnowledgeChunkVector(
                build_id=other,
                citation_id=prefix + "moon-fifth@1",
                content_sha256="0" * 64,
                embedding=[1.0] + [0.0] * (DIMENSION - 1),
            )
        )
    assert isinstance(failure.value.orig, ForeignKeyViolation)
    tie_source = "test-pgvector-ranking-tie"
    import_manifest(
        db_session,
        parse_manifest(canonical_bytes(payload(tie_source, "test"))),
        allow_test=True,
    )
    tie_id = tie_source + "@1/moon-fifth@1"
    assert embed_chunk(db_session, build, provider, tie_id, purpose="test")
    candidates = (
        select(KnowledgeChunk, KnowledgeSource)
        .join(KnowledgeSource)
        .where(
            KnowledgeSource.collection == "test",
            KnowledgeChunk.topic.in_(("planet_general", "planet_in_house")),
        )
    )
    query = (3.0, 1.0) + (0.0,) * (DIMENSION - 2)
    distance = KnowledgeChunkVector.embedding.cosine_distance(list(query))
    ranked = order_by_cosine(vector_candidates(candidates, build), query).add_columns(distance)
    actual = [(chunk.citation_id, value) for chunk, _, value in db_session.execute(ranked)]
    expected = {
        prefix + "moon-fifth@1": 1 - 3 / hypot(3, 1),
        tie_id: 1 - 3 / hypot(3, 1),
        prefix + "moon-general@1": 1 - 1 / hypot(3, 1),
    }
    assert [citation for citation, _ in actual] == sorted(
        expected, key=lambda citation: (expected[citation], citation)
    )
    assert [value for _, value in actual] == pytest.approx(
        [expected[citation] for citation, _ in actual],
        abs=1e-6,
    )


def test_encrypted_profile_crud_and_ownership(
    client: TestClient, db_session: Session, user_factory: Any
) -> None:
    def headers(email: str) -> dict[str, str]:
        user_factory(email=email, password="IntegrationTest2026!")
        login = client.post(
            "/api/v1/auth/login", json={"email": email, "password": "IntegrationTest2026!"}
        )
        assert login.status_code == 200
        return {"Authorization": f"Bearer {login.json()['access_token']}"}

    owner = headers("owner@example.com")
    stranger = headers("stranger@example.com")
    created = client.post(
        "/api/v1/profiles",
        headers=owner,
        json={
            "label": "Synthetic sample",
            "input_calendar": "AD",
            "entered_date": "2000-01-01",
            "time_certainty": "exact",
            "time_local": "12:00",
            "place_name": "Synthetic place",
            "latitude": 27.7,
            "longitude": 85.3,
            "timezone": "Asia/Kathmandu",
        },
    )
    assert created.status_code == 201
    profile_id = created.json()["id"]
    row = db_session.execute(
        text(
            "SELECT label_enc, entered_date_enc, time_local_enc, "
            "latitude_enc, longitude_enc, date_ad_enc, place_name_enc, timezone_enc "
            "FROM birth_profiles WHERE id = :id"
        ),
        {"id": uuid.UUID(profile_id)},
    ).one()
    assert all(isinstance(value, bytes) and value.startswith(b"gAAAAA") for value in row)

    path = f"/api/v1/profiles/{profile_id}"
    assert client.get(path, headers=owner).json()["label"] == "Synthetic sample"
    assert client.get(path, headers=stranger).status_code == 404
    assert client.patch(path, headers=stranger, json={"label": "Wrong owner"}).status_code == 404
    assert client.delete(path, headers=stranger).status_code == 404
    updated = client.patch(path, headers=owner, json={"label": "Updated sample"})
    assert updated.status_code == 200
    assert updated.json()["label"] == "Updated sample"
    assert client.delete(path, headers=owner).status_code == 204
    assert client.get(path, headers=owner).status_code == 404


def _run_blocked_race[T](
    engine: Engine,
    hold_lock: Callable[[Session], object],
    first: Callable[[Session], T],
    second: Callable[[Session], None],
) -> T:
    """Require PostgreSQL to report real blocking before committing the first transaction."""
    pids: Queue[int] = Queue()

    def run_second() -> None:
        with Session(engine) as db:
            db.execute(text("SET LOCAL lock_timeout = '20s'"))
            pid = db.scalar(text("SELECT pg_backend_pid()"))
            assert isinstance(pid, int)
            pids.put(pid)
            second(db)

    with ThreadPoolExecutor(max_workers=1) as workers:
        with Session(engine) as db, engine.connect() as observer:
            db.execute(text("SET LOCAL lock_timeout = '20s'"))
            first_pid = db.scalar(text("SELECT pg_backend_pid()"))
            hold_lock(db)
            pending = workers.submit(run_second)
            second_pid = pids.get(timeout=10)
            assert first_pid != second_pid

            deadline = monotonic() + 10
            poll = Event()
            while not observer.scalar(
                text("SELECT :holder = ANY(pg_blocking_pids(:waiter))"),
                {"holder": first_pid, "waiter": second_pid},
            ):
                assert not pending.done(), "Second operation completed without taking the lock"
                assert monotonic() < deadline, "PostgreSQL never reported the expected wait"
                poll.wait(0.02)
            result = first(db)
        pending.result(timeout=25)
    return result


def test_postgres_pgvector_duplicate_write_is_idempotent(migrated_engine: Engine) -> None:
    provider = SyntheticEmbeddingProvider()
    citation_id = "test-vector-race@1/moon-fifth@1"
    with Session(migrated_engine) as session:
        build_id = register_build(session, provider.config, purpose="test", generation=703)
        manifest = parse_manifest(canonical_bytes(payload("test-vector-race", "test")))
        import_manifest(session, manifest, allow_test=True)

    rolled_back_id = "test-vector-race@1/moon-general@1"
    with migrated_engine.connect() as connection, connection.begin() as transaction:
        with Session(bind=connection) as writer:
            assert embed_chunk(writer, build_id, provider, rolled_back_id, purpose="test")
        transaction.rollback()
    with Session(migrated_engine) as session:
        assert session.get(KnowledgeChunkVector, (build_id, rolled_back_id)) is None

    def write(session: Session, *, expected: bool) -> None:
        # The service owns its inner transaction. The harness controls the outer commit.
        with Session(bind=session.connection()) as writer:
            assert embed_chunk(writer, build_id, provider, citation_id, purpose="test") == expected

    _run_blocked_race(
        migrated_engine,
        lambda session: write(session, expected=True),
        lambda session: session.commit(),
        lambda session: write(session, expected=False),
    )
    with Session(migrated_engine) as session:
        rows = list(
            session.scalars(
                select(KnowledgeChunkVector).where(
                    KnowledgeChunkVector.build_id == build_id,
                    KnowledgeChunkVector.citation_id == citation_id,
                )
            )
        )
        assert len(rows) == 1
        assert len(rows[0].embedding) == DIMENSION


def test_postgres_pgvector_semantic_filters_and_conditionality(
    migrated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FixedQuery(SyntheticEmbeddingProvider):
        def embed_query(self, query: EmbeddingQuery) -> tuple[float, ...]:
            return (1.0,) + (0.0,) * (DIMENSION - 1)

    provider = FixedQuery()
    intent = EmbeddingQuery.model_validate(
        {
            "targets": [{"topic": "planet_in_house", "planet": "Moon", "house": 5}],
        }
    )
    search = Search(
        query="opaque unrelated wording",
        topics=("planet_in_house",),
        languages=("en",),
        limit=1,
        placements=(
            PlacementEvidence(planet="Moon", house=5, certainty="approximate"),
            PlacementEvidence(planet="Venus", house=4, certainty="exact"),
        ),
    )
    # Serving-shaped stand-ins and vectors are all rolled back. No production build is created.
    with migrated_engine.connect() as connection, connection.begin() as transaction:
        with Session(bind=connection) as session:
            build_id = register_build(session, provider.config, purpose="test", generation=704)
            for state in ("eligible", "disabled", "withdrawn", "pending", "hard-negative"):
                source_id = f"fixture-vector-{state}"
                data = payload(source_id)
                data["source"]["rights"]["permitted_uses"].append("third_party_processing")
                if state == "hard-negative":
                    data["chunks"][1]["applicability"]["planet"] = "Venus"
                import_manifest(session, parse_manifest(canonical_bytes(data)))
            for state in ("eligible", "disabled", "withdrawn", "pending", "hard-negative"):
                source_id = f"fixture-vector-{state}"
                source = session.get(KnowledgeSource, (source_id, 1))
                assert source is not None
                source.enabled = state not in {"disabled", "withdrawn"}
                source.publication_review = "rolled-back test only"
                if state == "withdrawn":
                    source.rights_status = "excluded"
                chunk = session.get(KnowledgeChunk, f"{source_id}@1/moon-fifth@1")
                assert chunk is not None
                if state != "pending":
                    chunk.editorial_status = "approved"
                    chunk.editorial_review = "rolled-back test only"
                # Ineligible entries have closer vectors and must never win this top-1 lookup.
                pair = [0.0, 1.0] if state == "eligible" else [1.0, 0.0]
                session.add(
                    KnowledgeChunkVector(
                        build_id=build_id,
                        citation_id=chunk.citation_id,
                        content_sha256=chunk.content_sha256,
                        embedding=pair + [0.0] * (DIMENSION - 2),
                    )
                )
            session.flush()
            assert retrieve(session, search) == ()
            with pytest.raises(BuildCompatibilityError):
                semantic_retrieval.retrieve_semantic(
                    session,
                    search,
                    intent,
                    build_id=build_id,
                    provider=provider,
                )
            # Bypass only the test-build gate, after checking it. Exercise actual serving SQL.
            monkeypatch.setattr(
                semantic_retrieval,
                "load_build",
                lambda db, identity, config, *, purpose: load_build(
                    db,
                    identity,
                    config,
                    purpose="test",
                ),
            )
            result = semantic_retrieval.retrieve_semantic(
                session,
                search,
                intent,
                build_id=build_id,
                provider=provider,
            )
            assert result.mode == "semantic"
            (match,) = result.matches
            assert match.citation_id == "fixture-vector-eligible@1/moon-fifth@1"
            assert match.conditional
            transaction.rollback()


def test_postgres_knowledge_ingestion_atomicity_and_revision_conflicts(db_session: Session) -> None:
    source_id = "fixture-knowledge-import"
    manifest = parse_manifest(canonical_bytes(payload(source_id)))

    def reject_chunk(session: Session, *args: object) -> None:
        for row in session.new:
            if isinstance(row, KnowledgeChunk):
                row.editorial_status = "invalid"

    event.listen(db_session, "before_flush", reject_chunk)
    try:
        with pytest.raises(IntegrityError) as failure:
            import_manifest(db_session, manifest)
        assert isinstance(failure.value.orig, CheckViolation)
        assert failure.value.orig.diag.constraint_name == "ck_knowledge_chunk_review"
    finally:
        event.remove(db_session, "before_flush", reject_chunk)
    assert db_session.get(KnowledgeSource, (source_id, 1)) is None
    assert (
        db_session.scalar(select(KnowledgeChunk).where(KnowledgeChunk.source_id == source_id))
        is None
    )
    db_session.rollback()
    assert import_manifest(db_session, manifest).inserted
    assert not import_manifest(db_session, manifest).inserted
    for version in (1, 2):
        changed = parse_manifest(
            canonical_bytes(payload(source_id, version=version, text="Changed."))
        )
        with pytest.raises(ManifestConflict):
            import_manifest(db_session, changed)
    assert db_session.get(KnowledgeSource, (source_id, 2)) is None
    chunks = list(
        db_session.scalars(select(KnowledgeChunk).where(KnowledgeChunk.source_id == source_id))
    )
    assert len(chunks) == len(manifest.chunks)
    assert all(chunk.editorial_status == "pending" for chunk in chunks)


def test_postgres_knowledge_competing_publications(migrated_engine: Engine) -> None:
    source_id = "fixture-knowledge-race"
    with Session(migrated_engine) as session:
        for version in (1, 2):
            import_manifest(
                session, parse_manifest(canonical_bytes(payload(source_id, version=version)))
            )

    def enable(session: Session, version: int) -> None:
        session.execute(
            update(KnowledgeSource)
            .where(
                KnowledgeSource.source_id == source_id,
                KnowledgeSource.version == version,
            )
            .values(enabled=True, publication_review="disposable synthetic race")
        )

    def compete(session: Session) -> None:
        with pytest.raises(IntegrityError) as failure:
            enable(session, 2)
        assert isinstance(failure.value.orig, UniqueViolation)
        assert failure.value.orig.diag.constraint_name == "uq_knowledge_enabled_source"
        session.rollback()

    _run_blocked_race(migrated_engine, lambda db: enable(db, 1), lambda db: db.commit(), compete)
    with Session(migrated_engine) as session:
        assert list(
            session.scalars(
                select(KnowledgeSource.version).where(
                    KnowledgeSource.source_id == source_id,
                    KnowledgeSource.enabled,
                )
            )
        ) == [1]


def test_postgres_knowledge_retrieval_and_citation_gates(db_session: Session) -> None:
    source_id = "fixture-knowledge-serving"
    test_id = "test-knowledge-serving"
    uncleared = payload("fixture-knowledge-uncleared")
    uncleared["source"]["rights"].update(status="unresolved", permitted_uses=[])
    for data in (payload(source_id), payload(test_id, "test"), uncleared):
        import_manifest(db_session, parse_manifest(canonical_bytes(data)), allow_test=True)
    query = Search(
        query="Moon fifth attention",
        topics=("planet_in_house",),
        languages=("en",),
        placements=(PlacementEvidence(planet="Moon", house=5, certainty="approximate"),),
    )
    assert retrieve(db_session, query) == ()
    db_session.rollback()

    def approve(source: str) -> None:
        db_session.execute(
            update(KnowledgeChunk)
            .where(
                KnowledgeChunk.source_id == source,
            )
            .values(editorial_status="approved", editorial_review="disposable synthetic approval")
        )

    with db_session.begin():
        for excluded in (test_id, "fixture-knowledge-uncleared"):
            approve(excluded)
            with pytest.raises(IntegrityError) as failure, db_session.begin_nested():
                db_session.execute(
                    update(KnowledgeSource)
                    .where(
                        KnowledgeSource.source_id == excluded,
                    )
                    .values(enabled=True, publication_review="disposable synthetic approval")
                )
            assert isinstance(failure.value.orig, CheckViolation)
            assert failure.value.orig.diag.constraint_name == "ck_knowledge_source_publication"
        db_session.execute(
            update(KnowledgeSource)
            .where(
                KnowledgeSource.source_id == source_id,
            )
            .values(enabled=True, publication_review="disposable synthetic approval")
        )
    assert retrieve(db_session, query) == ()  # Source enabled, chunks still pending.
    db_session.rollback()
    with db_session.begin():
        approve(source_id)
    (match,) = retrieve(db_session, query)
    assert match.source_id == source_id and match.conditional
    for facts in (
        (PlacementEvidence(planet="Moon", certainty="exact"),),
        (PlacementEvidence(planet="Moon", house=5, certainty="uncertain"),),
        (
            PlacementEvidence(planet="Moon", house=4, certainty="exact"),
            PlacementEvidence(planet="Venus", house=5, certainty="exact"),
        ),
    ):
        assert retrieve(db_session, query.model_copy(update={"placements": facts})) == ()
    db_session.rollback()
    with db_session.begin():
        db_session.execute(
            update(KnowledgeSource)
            .where(
                KnowledgeSource.source_id == source_id,
            )
            .values(enabled=False)
        )
    assert retrieve(db_session, query) == ()
    assert resolve_citation(db_session, match.citation_id) is not None
    db_session.rollback()
    with db_session.begin():
        db_session.execute(
            update(KnowledgeSource)
            .where(
                KnowledgeSource.source_id == source_id,
            )
            .values(rights_status="excluded")
        )
    assert resolve_citation(db_session, match.citation_id) is None


@pytest.mark.parametrize("operation", ["duplicate", "edit", "delete"])
def test_postgres_snapshot_write_serializes_with_profile_mutation(
    migrated_engine: Engine,
    db_session: Session,
    test_clock: FrozenClock,
    test_settings: Settings,
    user_factory: Any,
    operation: str,
) -> None:
    owner_id = user_factory(email=f"snapshot-{operation}@example.com").id
    created = create_profile(
        db_session,
        owner_id=owner_id,
        payload=BirthProfileCreate(
            label="Snapshot test",
            input_calendar=InputCalendar.AD,
            entered_date="2000-01-01",
            time_certainty=TimeCertainty.EXACT,
            time_local="12:00",
            place_name="Synthetic place",
            latitude=27.7,
            longitude=85.3,
            timezone="Asia/Kathmandu",
        ),
        clock=test_clock,
        settings=test_settings,
    )
    profile_id = created.id
    profile = db_session.get(BirthProfile, profile_id)
    assert profile is not None
    revision = profile.revision
    db_session.expunge(profile)
    db_session.rollback()
    result = calculate_profile_chart(
        profile, owner_id=owner_id, calc_settings=ChartSettings(), app_settings=test_settings
    )
    duplicates: list[uuid.UUID] = []

    def hold_profile(db: Session) -> None:
        db.execute(select(BirthProfile.id).where(BirthProfile.id == profile_id).with_for_update())

    def persist(db: Session) -> uuid.UUID:
        return persist_chart_snapshot(
            db, result, profile_revision=revision, owner_id=owner_id, app_settings=test_settings
        )

    def first(db: Session) -> uuid.UUID | None:
        if operation == "duplicate":
            return persist(db)
        target = db.get(BirthProfile, profile_id)
        assert target is not None
        if operation == "edit":
            update_profile(
                db,
                profile=target,
                owner_id=owner_id,
                payload=BirthProfileUpdate(label="Edited"),
                clock=test_clock,
                settings=test_settings,
            )
        else:
            delete_profile(db, profile=target, owner_id=owner_id)
        return None

    def second(db: Session) -> None:
        if operation == "duplicate":
            duplicates.append(persist(db))
        else:
            with pytest.raises(ChartProfileConflictError) as error:
                persist(db)
            assert error.value.code == "PROFILE_CHANGED"

    snapshot_id = _run_blocked_race(migrated_engine, hold_profile, first, second)
    with Session(migrated_engine) as db:
        rows = db.scalars(select(ChartSnapshot).where(ChartSnapshot.profile_id == profile_id)).all()
        if operation != "duplicate":
            assert rows == []
            return
        assert snapshot_id is not None and duplicates == [snapshot_id]
        assert len(rows) == 1
        saved = get_chart_snapshot(db, snapshot_id, owner_id=owner_id, app_settings=test_settings)
        assert saved is not None and saved.chart == result.chart
        row = rows[0]
        db.add(
            ChartSnapshot(
                id=uuid.uuid4(),
                profile_id=profile_id,
                profile_revision=revision,
                schema_version=row.schema_version,
                fingerprint_key=row.fingerprint_key,
                payload_enc=row.payload_enc,
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

        target = db.get(BirthProfile, profile_id)
        assert target is not None
        delete_profile(db, profile=target, owner_id=owner_id)
        assert db.get(ChartSnapshot, snapshot_id) is None


def test_concurrent_refresh_has_one_successor_and_replay_revokes_its_family(
    migrated_engine: Engine, db_session: Session, test_clock: FrozenClock, test_settings: Settings
) -> None:
    user = User(email="rotation@example.com", password_hash="unused-fixture")
    db_session.add(user)
    db_session.commit()
    user_id = user.id
    _, original = auth_service.create_token_pair(db_session, user, test_clock, test_settings)
    _, independent = auth_service.create_token_pair(db_session, user, test_clock, test_settings)

    def replay(db: Session) -> None:
        with pytest.raises(ValueError, match="Invalid or expired refresh token"):
            auth_service.refresh_tokens(db, original, test_clock, test_settings)

    _, replacement = _run_blocked_race(
        migrated_engine,
        lambda db: lock_user(db, user_id),
        lambda db: auth_service.refresh_tokens(db, original, test_clock, test_settings),
        replay,
    )
    with Session(migrated_engine) as db:
        tokens = db.scalars(select(RefreshToken).where(RefreshToken.user_id == user_id)).all()
        by_hash = {token.token_hash: token for token in tokens}
        old = by_hash[hash_token(original)]
        new = by_hash[hash_token(replacement)]
        assert len(tokens) == 3
        assert new.replaced_by_id == old.id and new.family_id == old.family_id
        assert old.revoked_at is not None and new.revoked_at is not None
        assert by_hash[hash_token(independent)].revoked_at is None
        assert db.scalars(select(AuditLog.action).where(AuditLog.actor_id == user_id)).all() == [
            "auth:token_reuse_detected"
        ]


@pytest.mark.parametrize("operation", ["logout", "reset"])
def test_waiting_session_revocation_includes_concurrent_refresh_replacement(
    migrated_engine: Engine,
    db_session: Session,
    test_clock: FrozenClock,
    test_settings: Settings,
    user_factory: Any,
    operation: str,
) -> None:
    user = user_factory(email=f"rotation-{operation}@example.com")
    user_id = user.id
    _, original = auth_service.create_token_pair(db_session, user, test_clock, test_settings)
    reset = auth_service.request_password_reset(
        db_session, user.email, test_clock, ConsoleMailer(environment="test"), test_settings
    )
    assert reset is not None

    def revoke(db: Session) -> None:
        if operation == "logout":
            assert auth_service.revoke_token(db, original, test_clock)
        else:
            auth_service.reset_password(db, reset, "NewFixturePassword2026!", test_clock, True)

    _, replacement = _run_blocked_race(
        migrated_engine,
        lambda db: lock_user(db, user_id),
        lambda db: auth_service.refresh_tokens(db, original, test_clock, test_settings),
        revoke,
    )
    with Session(migrated_engine) as db:
        token = db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(replacement))
        )
        assert token is not None and token.revoked_at is not None


def test_admin_deactivation_and_approval_cannot_remove_last_admin(
    migrated_engine: Engine, db_session: Session, test_clock: FrozenClock, user_factory: Any
) -> None:
    first_id = user_factory(
        email="first-admin@example.com",
        role=UserRole.ADMIN,
        astrologer_status=AstrologerStatus.PENDING,
    ).id
    second_id = user_factory(email="second-admin@example.com", role=UserRole.ADMIN).id

    def other_deactivation(db: Session) -> None:
        with pytest.raises(ValueError, match="Cannot deactivate the last admin"):
            user_service.deactivate_user(db, first_id, second_id, test_clock)

    _run_blocked_race(
        migrated_engine,
        lock_administration,
        lambda db: user_service.deactivate_user(db, second_id, first_id, test_clock),
        other_deactivation,
    )
    with Session(migrated_engine) as db:
        assert db.scalars(
            select(User.id).where(User.role == UserRole.ADMIN, User.is_active)
        ).all() == [first_id]
        assert db.scalars(
            select(AuditLog.action).where(AuditLog.target_id == str(second_id))
        ).all() == ["user:deactivate"]

    def legacy_approval(db: Session) -> None:
        with pytest.raises(ValueError, match="Cannot approve an administrator"):
            approve_astrologer(db, first_id, first_id, test_clock)

    _run_blocked_race(
        migrated_engine,
        lock_administration,
        lambda db: user_service.reactivate_user(db, second_id, first_id),
        legacy_approval,
    )

    def deactivate_after_approval(db: Session) -> None:
        user_service.deactivate_user(db, applicant_id, first_id, test_clock)

    applicant_id = user_factory(
        email="racing-applicant@example.com", astrologer_status=AstrologerStatus.PENDING
    ).id
    _run_blocked_race(
        migrated_engine,
        lock_administration,
        lambda db: approve_astrologer(db, applicant_id, first_id, test_clock),
        deactivate_after_approval,
    )
    with Session(migrated_engine) as db:
        first, second, applicant = (
            db.get(User, key) for key in (first_id, second_id, applicant_id)
        )
        assert first is not None and first.is_active and first.role == UserRole.ADMIN
        assert second is not None and second.is_active and second.role == UserRole.ADMIN
        assert (
            applicant is not None
            and not applicant.is_active
            and applicant.role == UserRole.ASTROLOGER
        )
        profile = db.get(AstrologerProfile, first_id)
        assert profile is not None and profile.status == AstrologerStatus.PENDING
        assert (
            db.scalars(select(AuditLog.action).where(AuditLog.target_id == str(first_id))).all()
            == []
        )


def test_postgres_audit_failure_rolls_back_deactivation_and_token_revocation(
    migrated_engine: Engine,
    db_session: Session,
    test_clock: FrozenClock,
    test_settings: Settings,
    user_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_id = user_factory(email="audit-admin@example.com", role=UserRole.ADMIN).id
    account = user_factory(email="audit-target@example.com")
    account_id = account.id
    _, raw = auth_service.create_token_pair(db_session, account, test_clock, test_settings)

    def fail_after_audit(*args: Any, **kwargs: Any) -> None:
        log_action(*args, **kwargs)
        raise RuntimeError("Audit failure")

    monkeypatch.setattr(user_service, "log_action", fail_after_audit)
    with pytest.raises(RuntimeError, match="Audit failure"), Session(migrated_engine) as db:
        user_service.deactivate_user(db, account_id, admin_id, test_clock)

    with Session(migrated_engine) as db:
        user = db.get(User, account_id)
        assert user is not None and user.is_active
        token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw)))
        assert token is not None and token.revoked_at is None
        assert db.scalar(select(AuditLog.id).where(AuditLog.target_id == str(account_id))) is None
