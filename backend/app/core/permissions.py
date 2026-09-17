"""RBAC: Keycloak realm role -> FastAPI permissions.

Roles: admin, manager, curator, user (realm roles from Keycloak `rtk`).
Domain objects (universities/workflow) are NOT implemented at this stage —
permissions exist only to verify the RBAC mechanism.
"""
from fastapi import Depends, HTTPException

from app.core.security import CurrentUser, get_current_user

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {"*"},
    "manager": {
        "university.read",
        "workflow.read",
        "reports.read",
    },
    "curator": {
        "university.read",
        "university.edit",
        "workflow.read",
        "workflow.change_status",
    },
    "user": {
        "university.read",
    },
}


def user_permissions(user: CurrentUser) -> set[str]:
    perms: set[str] = set()
    for role in user.roles or set():
        perms |= ROLE_PERMISSIONS.get(role, set())
    return perms


def require_permission(permission: str):
    def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        perms = user_permissions(user)
        if "*" in perms or permission in perms:
            return user
        raise HTTPException(status_code=403, detail=f"Forbidden: need {permission}")

    return checker


def require_role(*roles: str):
    def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if set(user.roles or set()) & set(roles) or "admin" in (user.roles or set()):
            return user
        raise HTTPException(status_code=403, detail=f"Forbidden: need one of {roles}")

    return checker
