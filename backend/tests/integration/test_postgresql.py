"""Opt-in integration checks. Use a fresh, independently selected disposable database."""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
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
from psycopg.errors import CheckViolation
from sqlalchemy import insert, inspect, select, text, update
from sqlalchemy.engine import URL, Connection, Engine, Row
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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
    RefreshToken,
    TimeCertainty,
    User,
)
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
            command.upgrade(cfg, "head")
        yield MigratedDatabase(engine, legacy)
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
            == "0005_resolved_bs_profiles"
        )
        assert connection.scalar(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        )
        assert set(Base.metadata.tables) <= set(
            inspect(connection).get_table_names(schema="public")
        )
        migration = MigrationContext.configure(connection, opts={"compare_server_default": True})
        assert compare_metadata(migration, Base.metadata) == []


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
