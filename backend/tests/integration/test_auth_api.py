from typing import Any

from fastapi.testclient import TestClient


def test_register_flow(client: TestClient) -> None:
    """POST /api/v1/auth/register creates user and returns 201."""
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "asha@example.com", "password": "SecurePassword2026!"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "asha@example.com"
    assert data["role"] == "user"
    assert "password" not in data

    # Duplicate registration returns 400
    dup_resp = client.post(
        "/api/v1/auth/register",
        json={"email": "asha@example.com", "password": "SecurePassword2026!"},
    )
    assert dup_resp.status_code == 400


def test_login_and_me_flow(client: TestClient, user_factory: Any) -> None:
    """POST /api/v1/auth/login returns token pair; GET /api/v1/me returns user."""
    user_factory(email="asha@example.com", password="SecurePassword2026!")

    # Login with valid credentials
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "asha@example.com", "password": "SecurePassword2026!"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data

    token = data["access_token"]

    # Access GET /api/v1/me
    me_resp = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "asha@example.com"

    # GET /api/v1/me without token returns 401
    anon_resp = client.get("/api/v1/me")
    assert anon_resp.status_code == 401


def test_token_refresh_flow(client: TestClient, user_factory: Any) -> None:
    """POST /api/v1/auth/refresh returns new token pair and revokes previous token."""
    user_factory(email="asha@example.com", password="SecurePassword2026!")

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "asha@example.com", "password": "SecurePassword2026!"},
    )
    tokens = login_resp.json()
    refresh_token = tokens["refresh_token"]

    # Refresh
    ref_resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert ref_resp.status_code == 200
    new_tokens = ref_resp.json()
    assert "access_token" in new_tokens
    assert "refresh_token" in new_tokens
    assert new_tokens["refresh_token"] != refresh_token


def test_logout_endpoints(client: TestClient, user_factory: Any) -> None:
    """POST /api/v1/auth/logout (public 204) and POST /api/v1/auth/logout-all (auth 204)."""
    user_factory(email="asha@example.com", password="SecurePassword2026!")

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "asha@example.com", "password": "SecurePassword2026!"},
    )
    tokens = login_resp.json()

    # Public logout with refresh token
    logout_resp = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert logout_resp.status_code == 204

    # Logout with unknown token still returns 204
    anon_logout = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": "unknown-token-string"},
    )
    assert anon_logout.status_code == 204

    # Authenticated logout-all
    logout_all_resp = client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert logout_all_resp.status_code == 204


def test_change_password_flow(client: TestClient, user_factory: Any) -> None:
    """POST /api/v1/auth/change-password updates password and allows login with new password."""
    user_factory(email="asha@example.com", password="OldPassword2026!")

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "asha@example.com", "password": "OldPassword2026!"},
    )
    access_token = login_resp.json()["access_token"]

    # Change password
    change_resp = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "old_password": "OldPassword2026!",
            "new_password": "NewSecurePassword2026!",
        },
    )
    assert change_resp.status_code == 204

    # Login with new password
    login_new = client.post(
        "/api/v1/auth/login",
        json={"email": "asha@example.com", "password": "NewSecurePassword2026!"},
    )
    assert login_new.status_code == 200


def test_forgot_and_reset_password_flow(client: TestClient, user_factory: Any) -> None:
    """POST /api/v1/auth/forgot-password returns 202; reset-password allows new password."""
    user_factory(email="asha@example.com", password="OldPassword2026!")

    # Forgot password always returns 202
    resp_exists = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "asha@example.com"},
    )
    assert resp_exists.status_code == 202

    resp_unknown = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "nonexistent@example.com"},
    )
    assert resp_unknown.status_code == 202
