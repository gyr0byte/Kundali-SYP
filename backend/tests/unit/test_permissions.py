"""Unit tests for RBAC permissions and role mapping."""

from app.core.permissions import (
    ROLE_PERMISSIONS,
    Permission,
    UserRole,
    has_permission,
)


def test_permission_enum_contains_all_twelve_prompt_permissions() -> None:
    """Verify all 12 required permissions from the project plan prompt exist."""
    required = {
        "profile:manage_own",
        "chart:read_own",
        "chat:use",
        "astrologer:apply",
        "review:read_queue",
        "review:decide",
        "knowledge:author",
        "admin:astrologers_manage",
        "admin:users_manage",
        "admin:audit_read",
        "admin:metrics_read",
        "account:self",
    }
    actual = {p.value for p in Permission}
    assert required.issubset(actual)


def test_user_role_permissions() -> None:
    """User role has self-account, profile, chart, chat, and apply permissions."""
    user_perms = ROLE_PERMISSIONS[UserRole.USER]
    assert Permission.ACCOUNT_SELF in user_perms
    assert Permission.PROFILE_MANAGE_OWN in user_perms
    assert Permission.CHART_READ_OWN in user_perms
    assert Permission.CHAT_USE in user_perms
    assert Permission.ASTROLOGER_APPLY in user_perms

    # Should not have astrologer review or admin rights
    assert Permission.REVIEW_READ_QUEUE not in user_perms
    assert Permission.ADMIN_USERS_MANAGE not in user_perms


def test_astrologer_role_permissions() -> None:
    """Astrologer role inherits user permissions plus review and knowledge authoring."""
    astro_perms = ROLE_PERMISSIONS[UserRole.ASTROLOGER]
    assert Permission.ACCOUNT_SELF in astro_perms
    assert Permission.CHAT_USE in astro_perms
    assert Permission.REVIEW_READ_QUEUE in astro_perms
    assert Permission.REVIEW_DECIDE in astro_perms
    assert Permission.KNOWLEDGE_AUTHOR in astro_perms

    # Should not have admin rights
    assert Permission.ADMIN_USERS_MANAGE not in astro_perms
    assert Permission.ADMIN_ASTROLOGERS_MANAGE not in astro_perms


def test_admin_role_permissions() -> None:
    """Admin role has all permissions including user, astrologer, and admin capabilities."""
    admin_perms = ROLE_PERMISSIONS[UserRole.ADMIN]
    for perm in Permission:
        assert perm in admin_perms


def test_has_permission_helper() -> None:
    """Test helper for checking user role permissions."""
    assert has_permission(UserRole.USER, Permission.CHAT_USE) is True
    assert has_permission(UserRole.USER, Permission.ADMIN_USERS_MANAGE) is False
    assert has_permission(UserRole.ADMIN, Permission.ADMIN_USERS_MANAGE) is True
