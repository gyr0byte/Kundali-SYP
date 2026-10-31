"""Role-based access control (RBAC) permissions and role mapping."""

from collections.abc import Callable, Sequence
from enum import Enum
from typing import Any

from fastapi import HTTPException, status


class UserRole(str, Enum):
    """User roles supported by the system."""

    USER = "user"
    ASTROLOGER = "astrologer"
    ADMIN = "admin"


class Permission(str, Enum):
    """Fine-grained permission identifiers."""

    ACCOUNT_SELF = "account:self"
    PROFILE_MANAGE_OWN = "profile:manage_own"
    CHART_READ_OWN = "chart:read_own"
    CHAT_USE = "chat:use"
    ASTROLOGER_APPLY = "astrologer:apply"
    REVIEW_READ_QUEUE = "review:read_queue"
    REVIEW_DECIDE = "review:decide"
    KNOWLEDGE_AUTHOR = "knowledge:author"
    ADMIN_ASTROLOGERS_MANAGE = "admin:astrologers_manage"
    ADMIN_USERS_MANAGE = "admin:users_manage"
    ADMIN_AUDIT_READ = "admin:audit_read"
    ADMIN_METRICS_READ = "admin:metrics_read"


# Complete mapping of roles to sets of allowed permissions
ROLE_PERMISSIONS: dict[UserRole, set[Permission]] = {
    UserRole.USER: {
        Permission.ACCOUNT_SELF,
        Permission.PROFILE_MANAGE_OWN,
        Permission.CHART_READ_OWN,
        Permission.CHAT_USE,
        Permission.ASTROLOGER_APPLY,
    },
    UserRole.ASTROLOGER: {
        # Inherits user capabilities
        Permission.ACCOUNT_SELF,
        Permission.PROFILE_MANAGE_OWN,
        Permission.CHART_READ_OWN,
        Permission.CHAT_USE,
        Permission.ASTROLOGER_APPLY,
        # Astrologer-specific capabilities
        Permission.REVIEW_READ_QUEUE,
        Permission.REVIEW_DECIDE,
        Permission.KNOWLEDGE_AUTHOR,
    },
    UserRole.ADMIN: {
        # All permissions
        perm
        for perm in Permission
    },
}


def has_permission(role: UserRole, permission: Permission) -> bool:
    """Check if a role possesses the specified permission."""
    perms = ROLE_PERMISSIONS.get(role, set())
    return permission in perms


def require_role(
    *allowed_roles: UserRole,
) -> Callable[..., Any]:
    """Dependency factory checking that the current user has one of the allowed roles."""

    def _role_checker(current_user: Any = None) -> Any:
        # Note: current_user will be resolved by FastAPI dependency injection
        # or checked directly when passed.
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        role = getattr(current_user, "role", None)
        if isinstance(role, str):
            try:
                role = UserRole(role)
            except ValueError:
                role = None

        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return _role_checker


def require_permission(
    permission: Permission,
) -> Callable[..., Any]:
    """Dependency factory checking that current user's role has the required permission."""

    def _permission_checker(current_user: Any = None) -> Any:
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        role = getattr(current_user, "role", None)
        if isinstance(role, str):
            try:
                role = UserRole(role)
            except ValueError:
                role = None

        if not role or not has_permission(role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return _permission_checker
