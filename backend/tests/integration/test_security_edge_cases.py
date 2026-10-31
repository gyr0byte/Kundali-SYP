"""Integration tests for security edge cases, audit hygiene, token families, and CORS."""

import json
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.permissions import UserRole
from app.core.security import create_access_token
from app.db.models.audit_log import AuditLog
from app.main import create_app


def test_logout_with_expired_access_token(client: TestClient, user_factory: Any) -> None:
    """POST /auth/logout uses refresh token to revoke session; it succeeds (204) even if access token is expired."""
    user = user_factory(email="logout_expired@example.com", password="SecurePassword2026!")

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "logout_expired@example.com", "password": "SecurePassword2026!"},
    )
    assert login_resp.status_code == 200
    refresh_token = login_resp.json()["refresh_token"]

    # Craft an expired access token
    settings = Settings(JWT_SECRET="x" * 32, DATABASE_URL="sqlite:///:memory:")
    expired_token = create_access_token(
        data={"sub": str(user.id), "role": user.role.value},
        secret_key=settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
        expires_minutes=-10,  # in the past
    )

    resp = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert resp.status_code == 204

    # The refresh token is now revoked
    refresh_resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_resp.status_code == 401


def test_unknown_token_logout_idempotent_no_audit(
    client: TestClient,
    db_session: Session,
) -> None:
    """Logging out an unknown token returns 204 without leaking state or creating audit rows."""
    initial_count = db_session.scalar(select(AuditLog).count()) or 0

    fake_token = "non_existent_refresh_token_1234567890abcdef"
    resp = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": fake_token},
    )
    assert resp.status_code == 204

    final_count = db_session.scalar(select(AuditLog).count()) or 0
    assert final_count == initial_count


def test_no_passwords_or_tokens_in_audit_metadata(
    client: TestClient,
    db_session: Session,
    user_factory: Any,
) -> None:
    """Verify passwords, raw tokens, or hashes are never logged to AuditLog metadata."""
    secret_pass = "SuperSecretPassword123!"
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={"email": "audit_hygiene@example.com", "password": secret_pass},
    )
    assert reg_resp.status_code == 201
    refresh_token = reg_resp.json()["refresh_token"]
    access_token = reg_resp.json()["access_token"]

    # Do a refresh and password change
    client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})

    logs = db_session.scalars(select(AuditLog)).all()
    assert len(logs) > 0

    for log_entry in logs:
        meta_str = json.dumps(log_entry.event_metadata).lower()
        assert secret_pass.lower() not in meta_str
        assert refresh_token.lower() not in meta_str
        assert access_token.lower() not in meta_str
        assert "password" not in log_entry.event_metadata or log_entry.event_metadata["password"] == "[REDACTED]"
        assert "token" not in log_entry.event_metadata or log_entry.event_metadata["token"] == "[REDACTED]"


def test_cors_origin_enforcement(db_session: Session) -> None:
    """Requests with unallowed origins are not granted CORS headers."""
    settings = Settings(
        JWT_SECRET="x" * 32,
        DATABASE_URL="sqlite:///:memory:",
        CORS_ALLOWED_ORIGINS=["http://trusted-site.com"],
        ENVIRONMENT="test",
    )
    app = create_app(settings)

    with TestClient(app) as test_client:
        # Untrusted origin
        resp_untrusted = test_client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "http://evil-attacker.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert resp_untrusted.headers.get("access-control-allow-origin") != "http://evil-attacker.com"

        # Trusted origin
        resp_trusted = test_client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "http://trusted-site.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert resp_trusted.headers.get("access-control-allow-origin") == "http://trusted-site.com"


def test_startup_refusal_without_jwt_secret() -> None:
    """Application startup lifespan raises RuntimeError if JWT_SECRET is invalid/short."""
    with pytest.raises(Exception):
        Settings(JWT_SECRET="too-short", DATABASE_URL="sqlite:///:memory:")

    # If secret is whitespace or less than 32 chars
    with pytest.raises(ValueError, match="JWT_SECRET must be at least 32 characters"):
        Settings(JWT_SECRET="short", DATABASE_URL="sqlite:///:memory:")


def test_jwt_alg_none_and_invalid_signature_rejected(
    client: TestClient,
    user_factory: Any,
) -> None:
    """Tokens with alg='none' or forged signature are rejected with 401."""
    user = user_factory(email="tamper@example.com", role=UserRole.USER)

    # 1. alg="none"
    header = {"alg": "none", "typ": "JWT"}
    payload = {"sub": str(user.id), "role": user.role.value}
    # Unsigned token: base64(header) + "." + base64(payload) + "."
    none_token = jwt.encode(payload, key="", algorithm="none")

    resp_none = client.get("/api/v1/me", headers={"Authorization": f"Bearer {none_token}"})
    assert resp_none.status_code == 401

    # 2. Signed with different secret
    forged_token = jwt.encode(payload, key="wrong_secret_key_" + "y" * 20, algorithm="HS256")
    resp_forged = client.get("/api/v1/me", headers={"Authorization": f"Bearer {forged_token}"})
    assert resp_forged.status_code == 401


def test_token_reuse_detection_revokes_entire_family(
    client: TestClient,
    user_factory: Any,
) -> None:
    """Presenting an already-rotated refresh token revokes all tokens in that family immediately."""
    user_factory(email="family_reuse@example.com", password="SecurePassword2026!")

    # 1. Login to get generation 1
    r1 = client.post(
        "/api/v1/auth/login",
        json={"email": "family_reuse@example.com", "password": "SecurePassword2026!"},
    )
    assert r1.status_code == 200
    refresh_gen1 = r1.json()["refresh_token"]

    # 2. Refresh once to get generation 2
    r2 = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_gen1},
    )
    assert r2.status_code == 200
    refresh_gen2 = r2.json()["refresh_token"]

    # 3. Attacker uses generation 1 again (token reuse!)
    r3 = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_gen1},
    )
    assert r3.status_code == 401

    # 4. Now generation 2 must also be revoked and unusable!
    r4 = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_gen2},
    )
    assert r4.status_code == 401


def test_deactivated_user_cannot_access(
    client: TestClient,
    user_factory: Any,
) -> None:
    """Deactivated user cannot log in and existing access tokens become invalid."""
    user = user_factory(email="deactivated@example.com", password="SecurePassword2026!")

    # Login to obtain valid access token
    r_login = client.post(
        "/api/v1/auth/login",
        json={"email": "deactivated@example.com", "password": "SecurePassword2026!"},
    )
    assert r_login.status_code == 200
    token = r_login.json()["access_token"]

    # Deactivate the user
    user.is_active = False

    # Attempt to use access token
    resp_me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert resp_me.status_code == 401

    # Attempt to log in again
    resp_relogin = client.post(
        "/api/v1/auth/login",
        json={"email": "deactivated@example.com", "password": "SecurePassword2026!"},
    )
    assert resp_relogin.status_code == 401
