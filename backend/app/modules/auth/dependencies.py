"""Centralized auth dependencies (single import point for routers).

Do NOT copy JWT validation into routers — use these.
"""
from app.core.permissions import require_permission, require_role
from app.core.security import CurrentUser, get_current_user, user_permissions  # noqa: F401

__all__ = ["CurrentUser", "get_current_user", "require_role", "require_permission"]
