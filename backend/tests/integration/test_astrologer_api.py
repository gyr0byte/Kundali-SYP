"""Integration tests for astrologer application and review queue endpoints."""

from typing import Any

from fastapi.testclient import TestClient

from app.core.permissions import UserRole
from app.db.models import AstrologerStatus


def test_astrologer_apply_endpoint(client: TestClient, user_factory: Any) -> None:
    """Authenticated user submits astrologer application."""
    user = user_factory(email="applicant@example.com", role=UserRole.USER)

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "applicant@example.com", "password": "TestPassword2026!"},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        "/api/v1/astrologer/apply",
        headers=headers,
        json={
            "display_name": "Pt. Shastri",
            "credentials": "15 years experience, Jyotish Visharad",
            "tradition": "Parashari",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["display_name"] == "Pt. Shastri"


def test_review_queue_access_permissions(client: TestClient, user_factory: Any) -> None:
    """GET /api/v1/review/queue accessible by approved astrologers or admins, returning empty list."""
    admin = user_factory(email="admin@example.com", role=UserRole.ADMIN)
    approved_astro = user_factory(
        email="approved@example.com",
        role=UserRole.ASTROLOGER,
        astrologer_status=AstrologerStatus.APPROVED,
    )
    pending_astro = user_factory(
        email="pending@example.com",
        role=UserRole.USER,
        astrologer_status=AstrologerStatus.PENDING,
    )
    regular_user = user_factory(email="asha@example.com", role=UserRole.USER)

    def get_token(email: str) -> str:
        r = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "TestPassword2026!"},
        )
        return r.json()["access_token"]  # type: ignore[no-any-return]

    # Admin -> 200, []
    admin_token = get_token("admin@example.com")
    resp_admin = client.get("/api/v1/review/queue", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp_admin.status_code == 200
    assert resp_admin.json() == []

    # Approved Astrologer -> 200, []
    astro_token = get_token("approved@example.com")
    resp_astro = client.get("/api/v1/review/queue", headers={"Authorization": f"Bearer {astro_token}"})
    assert resp_astro.status_code == 200
    assert resp_astro.json() == []

    # Pending Astrologer -> 403 Forbidden
    pending_token = get_token("pending@example.com")
    resp_pending = client.get("/api/v1/review/queue", headers={"Authorization": f"Bearer {pending_token}"})
    assert resp_pending.status_code == 403

    # Regular User -> 403 Forbidden
    user_token = get_token("asha@example.com")
    resp_user = client.get("/api/v1/review/queue", headers={"Authorization": f"Bearer {user_token}"})
    assert resp_user.status_code == 403
