"""Canonical action permissions for public roles (user/manager/admin)."""

from types import MappingProxyType

from fastapi import Depends

from app.core.errors import SecurityError
from app.core.security import CurrentUser, get_current_user
from app.schemas.errors import ErrorCode

PUBLIC_ROLE_NAMES = frozenset({"user", "manager", "admin"})
USER_PERMISSIONS = frozenset({
    "assistant.use",
    "university.read", "catalog.read", "workflow.read",
    "workflow.change_status", "workflow.comment.create", "workflow.comment.update",
    "workflow.attachment.read", "workflow.attachment.create",
    "workflow.attachment.delete", "workflow.task.read", "workflow.task.update",
    "reports.read", "reports.create", "analytics.read", "import.read",
})
MANAGER_PERMISSIONS = (USER_PERMISSIONS - {"import.read"}) | frozenset({
    "university.edit", "university_responsible.manage", "analytics.extended",
    "audit.read", "user_university.manage",
})
ADMIN_PERMISSIONS = MANAGER_PERMISSIONS | frozenset({
    "catalog.manage", "import.read", "import.write",
    "university.create", "university.delete", "workflow_template.manage",
    "admin.users", "admin.settings", "*",
})
ROLE_PERMISSIONS = MappingProxyType({
    "user": USER_PERMISSIONS, "manager": MANAGER_PERMISSIONS,
    "admin": ADMIN_PERMISSIONS,
})
ALL_PERMISSIONS = ADMIN_PERMISSIONS


def effective_role(user: CurrentUser) -> str:
    """One P5 precedence for the role stored with business audit events."""
    roles = user.roles or set()
    for role in ("admin", "manager", "user"):
        if role in roles:
            return role
    return "user"


def user_permissions(user: CurrentUser) -> set[str]:
    roles = user.roles or set()
    if not roles & PUBLIC_ROLE_NAMES:
        return set()
    return set(ROLE_PERMISSIONS[effective_role(user)])


def require_permission(permission: str):
    if permission not in ALL_PERMISSIONS:
        raise ValueError(f"Unregistered permission: {permission}")

    def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        perms = user_permissions(user)
        if permission in perms:
            return user
        raise SecurityError(ErrorCode.FORBIDDEN)

    # Documentation reads these markers, never the checker's closure or docstring.
    checker.api_required_permission = permission
    return checker


def require_role(*roles: str):
    def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if set(user.roles or set()) & set(roles) or "admin" in (user.roles or set()):
            return user
        raise SecurityError(ErrorCode.FORBIDDEN)

    checker.api_allowed_roles = frozenset(roles) | {"admin"}
    return checker
