"""Opt-in integration checks. Use a fresh, independently selected disposable database."""

import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.engine import URL, Engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.connection import DatabaseConfigurationError, postgres_engine, postgres_url

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
def migrated_engine() -> Iterator[Engine]:
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
            command.upgrade(cfg, "head")
        yield engine
    except Exception:
        pytest.fail(
            "Disposable PostgreSQL setup failed. Check the target and permissions privately.",
            pytrace=False,
        )
    finally:
        if engine is not None:
            engine.dispose()


@pytest.fixture
def db_session(migrated_engine: Engine) -> Iterator[Session]:
    # App services commit. Use the one-use migrated database instead of a rollback-only fixture.
    with Session(migrated_engine, expire_on_commit=False) as session:
        yield session


def test_migrations_match_models_and_install_vector(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM public.alembic_version"))
            == "0003_enable_pgvector"
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
