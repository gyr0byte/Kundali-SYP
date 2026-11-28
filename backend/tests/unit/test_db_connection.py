"""Offline tests for PostgreSQL policy and checker diagnostics."""

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.db.connection import (
    DatabaseConfigurationError,
    DatabaseConnectionError,
    postgres_engine,
    postgres_url,
)

REPO = Path(__file__).resolve().parents[3]
FIXTURE = "postgresql://fixture:encoded%25value@db.example/kundali_test_probe"


@pytest.fixture(autouse=True)
def isolate_libpq_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PGSERVICE", raising=False)
    monkeypatch.delenv("PGHOSTADDR", raising=False)


@pytest.fixture
def checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_db", REPO / "scripts" / "check_db.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_postgres_policy_normalizes_without_connecting() -> None:
    url = postgres_url(FIXTURE, __file__)
    assert url.drivername == "postgresql+psycopg"
    assert url.password == "encoded%value"
    assert url.query["sslmode"] == "verify-full"
    assert url.query["connect_timeout"] == "5"
    assert url.query["channel_binding"] == "require"
    assert postgres_engine(url).hide_parameters


@pytest.mark.parametrize(
    "suffix", ["?sslmode=require", "?hostaddr=127.0.0.1", "?host=other.example"]
)
def test_postgres_policy_rejects_weak_tls_and_routing_overrides(suffix: str) -> None:
    with pytest.raises(DatabaseConfigurationError) as error:
        postgres_url(FIXTURE + suffix, __file__)
    assert "encoded" not in str(error.value)
    assert "db.example" not in str(error.value)


def test_missing_ca_fails_closed() -> None:
    with pytest.raises(DatabaseConfigurationError, match="KUNDALI_DB_CA_FILE"):
        postgres_url(FIXTURE, None)


def test_driver_connection_errors_are_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = postgres_engine(postgres_url(FIXTURE, __file__))

    def fake_connect(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("sensitive driver output")

    monkeypatch.setattr(engine.dialect, "connect", fake_connect)
    with pytest.raises(DatabaseConnectionError, match=r"^PostgreSQL connection failed\.$"):
        engine.connect()


def test_driver_refuses_a_connection_without_tls(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = postgres_engine(postgres_url(FIXTURE, __file__))
    connection = MagicMock()
    connection.pgconn.ssl_in_use = False
    monkeypatch.setattr(engine.dialect, "connect", lambda *args, **kwargs: connection)
    with pytest.raises(DatabaseConnectionError, match="did not negotiate TLS"):
        engine.connect()
    connection.close.assert_called_once()


def test_settings_exclude_secrets_from_diagnostics(test_settings: Settings) -> None:
    secrets = {"DATABASE_URL", "JWT_SECRET", "ENCRYPTION_KEY"}
    assert secrets.isdisjoint(test_settings.model_dump())
    assert all(f"{key}=" not in repr(test_settings) for key in secrets)


def test_checker_reports_known_statuses(checker: ModuleType) -> None:
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.connection.driver_connection.pgconn.ssl_in_use = True
    connection.scalar.side_effect = [1, True, False, True]
    connection.scalars.return_value.all.return_value = ["0002_birth_profiles_table"]
    assert checker.inspect_database(engine) == (
        "0002_birth_profiles_table",
        "available, not installed",
    )
    assert str(connection.execute.call_args_list[0].args[0]) == "SET TRANSACTION READ ONLY"


@pytest.mark.parametrize(
    ("revision", "reported", "exit_code"),
    [
        ("0007_knowledge_embeddings", "0007_knowledge_embeddings", 0),
        ("0006_knowledge_corpus", "0006_knowledge_corpus", 1),
        ("0005_resolved_bs_profiles", "0005_resolved_bs_profiles", 1),
        ("unrecognized_revision", "unknown", 1),
    ],
)
def test_checker_readiness_by_revision(
    checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    revision: str,
    reported: str,
    exit_code: int,
) -> None:
    monkeypatch.setenv("DATABASE_URL", FIXTURE)
    monkeypatch.setenv("KUNDALI_DB_CA_FILE", __file__)
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.connection.driver_connection.pgconn.ssl_in_use = True
    connection.scalar.side_effect = [1, True, True, True]
    connection.scalars.return_value.all.return_value = [revision]
    monkeypatch.setattr(checker, "postgres_engine", lambda _: engine)

    assert checker.main() == exit_code
    assert f"Alembic revision: {reported}\n" in capsys.readouterr().out
    engine.dispose.assert_called_once()


def test_checker_sanitizes_failure(
    checker: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", FIXTURE)
    monkeypatch.setenv("KUNDALI_DB_CA_FILE", __file__)
    engine = MagicMock()
    engine.connect.side_effect = RuntimeError(FIXTURE)
    monkeypatch.setattr(checker, "postgres_engine", lambda _: engine)
    assert checker.main() == 3
    assert capsys.readouterr().err == "PostgreSQL connectivity or inspection failed.\n"
    engine.dispose.assert_called_once()
