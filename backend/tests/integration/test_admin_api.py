"""Integration tests for admin management endpoints."""

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.permissions import UserRole
from app.core.security import create_access_token
from app.db.models import AstrologerStatus


def test_pre_promotion_access_token_cannot_gain_admin_access(
    client: TestClient, db_session: Session, test_settings: Settings, user_factory: Any
) -> None:
    user = user_factory()
    access = create_access_token(
        str(user.id), UserRole.USER, test_settings.JWT_SECRET, timedelta(minutes=5)
    )
    user.role = UserRole.ADMIN
    db_session.commit()
    response = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {access}"})
    assert response.status_code == 401


def test_admin_user_management(client: TestClient, user_factory: Any) -> None:
    """Admin lists users, deactivates a user, and reactivates a user."""
    user_factory(email="admin@example.com", role=UserRole.ADMIN)
    user = user_factory(email="asha@example.com", role=UserRole.USER)

    # Login as admin
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "TestPassword2026!"},
    )
    admin_token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # List users
    list_resp = client.get("/api/v1/admin/users", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] >= 2

    # Deactivate user
    deact_resp = client.post(f"/api/v1/admin/users/{user.id}/deactivate", headers=headers)
    assert deact_resp.status_code == 204

    # Reactivate user
    react_resp = client.post(f"/api/v1/admin/users/{user.id}/reactivate", headers=headers)
    assert react_resp.status_code == 204


def test_admin_astrologer_credentialing(client: TestClient, user_factory: Any) -> None:
    """Admin lists astrologers, approves application, and suspends astrologer."""
    user_factory(email="admin@example.com", role=UserRole.ADMIN)
    astro = user_factory(
        email="astro@example.com",
        role=UserRole.USER,
        astrologer_status=AstrologerStatus.PENDING,
    )

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "TestPassword2026!"},
    )
    admin_token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # List pending astrologers
    list_resp = client.get("/api/v1/admin/astrologers?status=pending", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1

    # Approve astrologer
    appr_resp = client.post(f"/api/v1/admin/astrologers/{astro.id}/approve", headers=headers)
    assert appr_resp.status_code == 204

    # Suspend astrologer
    susp_resp = client.post(f"/api/v1/admin/astrologers/{astro.id}/suspend", headers=headers)
    assert susp_resp.status_code == 204


def test_admin_audit_logs(client: TestClient, user_factory: Any) -> None:
    """Admin fetches paginated audit logs."""
    user_factory(email="admin@example.com", role=UserRole.ADMIN)

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "TestPassword2026!"},
    )
    admin_token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    audit_resp = client.get("/api/v1/admin/audit?limit=10&offset=0", headers=headers)
    assert audit_resp.status_code == 200
    data = audit_resp.json()
    assert "items" in data
    assert "total" in data
