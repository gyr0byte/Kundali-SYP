"""Integration tests for the full Role-Based Access Control (RBAC) matrix."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.permissions import UserRole
from app.db.models.astrologer_profile import AstrologerStatus


@pytest.fixture
def rbac_users(user_factory: Any) -> dict[str, Any]:
    """Create a user for each caller state."""
    users = {
        "user": user_factory(
            email="user_role@example.com",
            password="SecurePassword2026!",
            role=UserRole.USER,
        ),
        "pending_astrologer": user_factory(
            email="pending_astro@example.com",
            password="SecurePassword2026!",
            role=UserRole.USER,
            astrologer_status=AstrologerStatus.PENDING,
        ),
        "approved_astrologer": user_factory(
            email="approved_astro@example.com",
            password="SecurePassword2026!",
            role=UserRole.ASTROLOGER,
            astrologer_status=AstrologerStatus.APPROVED,
        ),
        "suspended_astrologer": user_factory(
            email="suspended_astro@example.com",
            password="SecurePassword2026!",
            role=UserRole.ASTROLOGER,
            astrologer_status=AstrologerStatus.SUSPENDED,
        ),
        "admin": user_factory(
            email="admin_role@example.com",
            password="SecurePassword2026!",
            role=UserRole.ADMIN,
        ),
    }
    return users


def _get_auth_header(client: TestClient, email: str | None) -> dict[str, str]:
    if email is None:
        return {}
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "SecurePassword2026!"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# Matrix test: endpoint, method, payload/params, expected status for each role:
# (anonymous, user, pending_astro, approved_astro, suspended_astro, admin)
RBAC_ENDPOINTS = [
    # 1. GET /api/v1/me
    ("GET", "/api/v1/me", None, {"anonymous": 401, "user": 200, "pending_astrologer": 200, "approved_astrologer": 200, "suspended_astrologer": 200, "admin": 200}),
    # 2. POST /api/v1/auth/logout-all
    ("POST", "/api/v1/auth/logout-all", None, {"anonymous": 401, "user": 204, "pending_astrologer": 204, "approved_astrologer": 204, "suspended_astrologer": 204, "admin": 204}),
    # 3. POST /api/v1/auth/change-password
    ("POST", "/api/v1/auth/change-password", {"old_password": "SecurePassword2026!", "new_password": "NewSecurePassword2026!"}, {"anonymous": 401, "user": 204, "pending_astrologer": 204, "approved_astrologer": 204, "suspended_astrologer": 204, "admin": 204}),
    # 4. POST /api/v1/astrologer/apply
    ("POST", "/api/v1/astrologer/apply", {"bio": "Experienced Vedic astrologer.", "years_experience": 10}, {"anonymous": 401, "user": 201, "pending_astrologer": 400, "approved_astrologer": 403, "suspended_astrologer": 403, "admin": 403}),
    # 5. GET /api/v1/review/queue
    ("GET", "/api/v1/review/queue", None, {"anonymous": 401, "user": 403, "pending_astrologer": 403, "approved_astrologer": 200, "suspended_astrologer": 403, "admin": 200}),
    # 6. GET /api/v1/admin/users
    ("GET", "/api/v1/admin/users", None, {"anonymous": 401, "user": 403, "pending_astrologer": 403, "approved_astrologer": 403, "suspended_astrologer": 403, "admin": 200}),
    # 7. GET /api/v1/admin/astrologers
    ("GET", "/api/v1/admin/astrologers", None, {"anonymous": 401, "user": 403, "pending_astrologer": 403, "approved_astrologer": 403, "suspended_astrologer": 403, "admin": 200}),
    # 8. GET /api/v1/admin/audit
    ("GET", "/api/v1/admin/audit", None, {"anonymous": 401, "user": 403, "pending_astrologer": 403, "approved_astrologer": 403, "suspended_astrologer": 403, "admin": 200}),
]


@pytest.mark.parametrize(
    "method,endpoint,payload,expected_statuses",
    RBAC_ENDPOINTS,
)
@pytest.mark.parametrize(
    "caller_role",
    ["anonymous", "user", "pending_astrologer", "approved_astrologer", "suspended_astrologer", "admin"],
)
def test_rbac_matrix_endpoint(
    client: TestClient,
    rbac_users: dict[str, Any],
    method: str,
    endpoint: str,
    payload: dict[str, Any] | None,
    expected_statuses: dict[str, int],
    caller_role: str,
) -> None:
    """Parametrized verification of all RBAC access rules across roles and endpoints."""
    email = None if caller_role == "anonymous" else rbac_users[caller_role].email
    headers = _get_auth_header(client, email)

    # For change-password, reset password back after test so other tests with same user work if any
    if method == "GET":
        resp = client.get(endpoint, headers=headers)
    elif method == "POST":
        resp = client.post(endpoint, json=payload, headers=headers)
        if endpoint == "/api/v1/auth/change-password" and resp.status_code == 204:
            # Change it back so user remains usable
            client.post(
                endpoint,
                json={"old_password": "NewSecurePassword2026!", "new_password": "SecurePassword2026!"},
                headers=headers,
            )
    else:
        raise ValueError(f"Unsupported method: {method}")

    expected = expected_statuses[caller_role]
    assert resp.status_code == expected, (
        f"Expected {expected} for {caller_role} on {method} {endpoint}, got {resp.status_code} ({resp.text})"
    )


def test_rbac_admin_mutations(
    client: TestClient,
    user_factory: Any,
) -> None:
    """Verify non-admin roles cannot mutate users or astrologer statuses."""
    target_user = user_factory(email="target@example.com", role=UserRole.USER)
    admin = user_factory(email="matrix_admin@example.com", role=UserRole.ADMIN)

    # User cannot deactivate target
    user_headers = _get_auth_header(client, target_user.email)
    resp = client.post(f"/api/v1/admin/users/{target_user.id}/deactivate", headers=user_headers)
    assert resp.status_code == 403

    # Admin can deactivate target
    admin_headers = _get_auth_header(client, admin.email)
    resp = client.post(f"/api/v1/admin/users/{target_user.id}/deactivate", headers=admin_headers)
    assert resp.status_code == 200

    # Non-existent target returns 404 for admin
    fake_id = uuid.uuid4()
    resp = client.post(f"/api/v1/admin/users/{fake_id}/deactivate", headers=admin_headers)
    assert resp.status_code == 404
