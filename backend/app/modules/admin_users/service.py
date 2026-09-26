"""Admin operations over one Keycloak identity source; PostgreSQL is audit/catalog only."""

from __future__ import annotations

import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.errors import BusinessException, ConflictError, SecurityError
from app.core.security import CurrentUser
from app.models.catalog import University
from app.modules.admin_users.keycloak_client import KeycloakAdminClient
from app.modules.admin_users.schemas import AdminUserOut, AdminUsersPage, UserInvite, UserScope, UserUpdate
from app.modules.audit.service import AuditAction, AuditService, context_for
from app.schemas.errors import ErrorCode

PUBLIC_ROLES = ("admin", "manager", "user")
MAX_LIST_USERS = 10_000


def _all_role_users(kc: KeycloakAdminClient, role: str) -> list[dict]:
    result: list[dict] = []
    for first in range(0, MAX_LIST_USERS, 100):
        chunk = kc.role_users(role, first=first, maximum=100)
        result.extend(chunk)
        if len(chunk) < 100:
            return result
    raise BusinessException(ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE)


def _role_memberships(kc: KeycloakAdminClient) -> dict[str, str]:
    # Three batch reads for the three existing realm roles, never a per-user
    # Admin API call for a table page.
    memberships: dict[str, str] = {}
    for role in PUBLIC_ROLES:
        for item in _all_role_users(kc, role):
            memberships.setdefault(item["id"], role)
    return memberships


def _searched_users(kc: KeycloakAdminClient, search: str) -> list[dict]:
    candidates: list[dict] = []
    for first in range(0, MAX_LIST_USERS, 100):
        chunk = kc.users(search=search, first=first, maximum=100)
        candidates.extend(chunk)
        if len(chunk) < 100:
            return candidates
    raise BusinessException(ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE)


def _scope(record: dict, role: str) -> UserScope:
    if role == "admin":
        return UserScope(kind="all")
    raw = (record.get("attributes") or {}).get("university_ids") or []
    values = raw if isinstance(raw, list) else [raw]
    ids = []
    for value in values:
        try:
            ids.append(uuid.UUID(str(value)))
        except (ValueError, TypeError, AttributeError):
            continue
    return UserScope(kind="universities", university_ids=ids)


def _dto(record: dict, role: str) -> AdminUserOut:
    name = " ".join(part for part in (record.get("firstName"), record.get("lastName")) if part).strip()
    return AdminUserOut(
        id=uuid.UUID(record["id"]), username=record.get("username") or "",
        name=name or record.get("username") or "", email=record.get("email") or "",
        role=role, status="active" if record.get("enabled", True) else "blocked",
        scope=_scope(record, role),
    )


def _user_role(kc: KeycloakAdminClient, user_id: str) -> str:
    names = {role.get("name") for role in kc.user_roles(user_id)}
    for role in PUBLIC_ROLES:
        if role in names:
            return role
    # Never guess a role for an unmanaged Keycloak account.
    raise BusinessException(ErrorCode.VALIDATION_ERROR)


def list_users(kc: KeycloakAdminClient, *, search: str, role: str | None,
               page: int, page_size: int) -> AdminUsersPage:
    memberships = _role_memberships(kc)
    # Keycloak's user-list representation has attributes but no realm roles;
    # role-users has roles but not reliable attributes. Aggregate both in a
    # bounded number of paged calls and paginate the joined result here.
    matched = [item for item in _searched_users(kc, search)
               if item["id"] in memberships and (role is None or memberships[item["id"]] == role)]
    total = len(matched)
    rows = matched[(page - 1) * page_size:page * page_size]
    return AdminUsersPage(items=[_dto(row, memberships[row["id"]]) for row in rows],
                          page=page, page_size=page_size, total=total)


def get_user(kc: KeycloakAdminClient, user_id: str) -> AdminUserOut:
    return _dto(kc.user(user_id), _user_role(kc, user_id))


def _validate_scope(db: Session, scope: UserScope) -> None:
    if scope.kind == "all":
        return
    ids = set(scope.university_ids)
    if len(ids) != len(scope.university_ids):
        raise BusinessException(ErrorCode.VALIDATION_ERROR)
    if ids:
        found = set(db.scalars(select(University.id).where(University.id.in_(ids))))
        if found != ids:
            raise BusinessException(ErrorCode.VALIDATION_ERROR)


def _last_admin_guard(db: Session, kc: KeycloakAdminClient, target: dict, role: str) -> None:
    if role != "admin" or not target.get("enabled", True):
        return
    # Serialize last-admin mutations across backend processes. Keycloak is
    # authoritative; the PostgreSQL lock is only a coordination primitive.
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(1010, 2026)"))
    active = [item for item in _all_role_users(kc, "admin") if item.get("enabled", True)]
    if len({item["id"] for item in active}) <= 1:
        raise ConflictError(field="role")


def _target_display_name(user: dict | None, fallback: str = "") -> str | None:
    """Human name for a Keycloak user dict. Never returns a UUID alone."""
    if not isinstance(user, dict):
        return None
    first = str(user.get("firstName") or "").strip()
    last = str(user.get("lastName") or "").strip()
    full = f"{first} {last}".strip()
    if full:
        return full
    for key in ("username", "email"):
        value = user.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback or None


def _audit(db: Session, actor: CurrentUser, target_id: str, kind: str, before=None, after=None,
           target_name: str | None = None) -> None:
    old_value: dict = {"audit_object_type": "user", "kind": kind, "value": before}
    new_value: dict = {"audit_object_type": "user", "kind": kind, "value": after}
    if target_name:
        old_value["target_name"] = target_name
        new_value["target_name"] = target_name
    AuditService(db).log_event(
        context=context_for(db, actor.id), action=AuditAction.ADMIN_CONFIG,
        entity_type="config", entity_id=uuid.UUID(target_id),
        old_value=old_value,
        new_value=new_value,
    )


def update_user(db: Session, kc: KeycloakAdminClient, actor: CurrentUser,
                user_id: str, change: UserUpdate) -> AdminUserOut:
    before = kc.user(user_id)
    old_role = _user_role(kc, user_id)
    if actor.id == user_id and change.role != "admin":
        raise SecurityError(ErrorCode.FORBIDDEN)
    if old_role == "admin" and change.role != "admin":
        _last_admin_guard(db, kc, before, old_role)
    _validate_scope(db, change.scope)
    old_attributes = dict(before.get("attributes") or {})
    next_attributes = dict(old_attributes)
    next_attributes["university_ids"] = [str(value) for value in change.scope.university_ids]
    if change.scope.kind != "all":
        kc.ensure_scope_mapper()
    scope_changed = old_attributes.get("university_ids", []) != next_attributes["university_ids"]
    role_changed = old_role != change.role
    if not scope_changed and not role_changed:
        return _dto(before, old_role)
    new_role = kc.role(change.role) if role_changed else None
    previous_role = kc.role(old_role) if role_changed else None
    assigned_new = False
    removed_old = False
    try:
        if scope_changed:
            kc.update_user(user_id, {**before, "attributes": next_attributes})
        if role_changed:
            kc.assign_role(user_id, new_role)
            assigned_new = True
            kc.remove_role(user_id, previous_role)
            removed_old = True
        if scope_changed:
            persisted = (kc.user(user_id).get("attributes") or {}).get("university_ids") or []
            if persisted != next_attributes["university_ids"]:
                raise BusinessException(ErrorCode.EXTERNAL_SYNC_FAILED)
        # A stale admin JWT is rejected by live_admin; end sessions for the
        # target so its next login receives the current role/scope claims.
        kc.logout(user_id)
    except Exception:
        try:
            if removed_old:
                kc.assign_role(user_id, previous_role)
            if assigned_new:
                kc.remove_role(user_id, new_role)
            if scope_changed:
                kc.update_user(user_id, before)
        except Exception as exc:
            raise BusinessException(ErrorCode.EXTERNAL_SYNC_FAILED) from exc
        raise
    # Already issued access tokens expire at the realm's 300-second TTL.
    target_name = _target_display_name(before)
    if role_changed:
        _audit(db, actor, user_id, "role", old_role, change.role, target_name)
    if scope_changed:
        _audit(db, actor, user_id, "scope", old_attributes.get("university_ids", []),
               next_attributes["university_ids"], target_name)
    db.commit()
    return _dto({**before, "attributes": next_attributes}, change.role)


def set_blocked(db: Session, kc: KeycloakAdminClient, actor: CurrentUser,
                user_id: str, blocked: bool) -> AdminUserOut:
    target = kc.user(user_id)
    old_role = _user_role(kc, user_id)
    if blocked and actor.id == user_id:
        raise SecurityError(ErrorCode.FORBIDDEN)
    if blocked:
        _last_admin_guard(db, kc, target, old_role)
    was_enabled = bool(target.get("enabled", True))
    if was_enabled == (not blocked):
        return _dto(target, old_role)
    kc.update_user(user_id, {**target, "enabled": not blocked})
    if blocked:
        try:
            kc.logout(user_id)
        except Exception:
            try:
                kc.update_user(user_id, target)
            except Exception as exc:
                raise BusinessException(ErrorCode.EXTERNAL_SYNC_FAILED) from exc
            raise
    _audit(db, actor, user_id, "status", "active" if was_enabled else "blocked",
           "blocked" if blocked else "active", _target_display_name(target))
    db.commit()
    return _dto({**target, "enabled": not blocked}, old_role)


def invite_user(db: Session, kc: KeycloakAdminClient, actor: CurrentUser,
                data: UserInvite) -> tuple[AdminUserOut, str]:
    _validate_scope(db, data.scope)
    kc.ensure_scope_mapper()
    name_parts = data.name.strip().split(" ", 1)
    payload = {
        "username": data.username, "email": data.email,
        "firstName": name_parts[0], "lastName": name_parts[1] if len(name_parts) > 1 else "",
        "enabled": True, "emailVerified": False,
        "requiredActions": ["UPDATE_PASSWORD"],
        "attributes": {"university_ids": [str(item) for item in data.scope.university_ids]},
    }
    user_id = kc.create_user(payload)
    try:
        kc.assign_role(user_id, kc.role(data.role))
        persisted = (kc.user(user_id).get("attributes") or {}).get("university_ids") or []
        if persisted != payload["attributes"]["university_ids"]:
            raise BusinessException(ErrorCode.EXTERNAL_SYNC_FAILED)
    except Exception:
        try:
            kc.delete_user(user_id)
        except Exception as exc:
            raise BusinessException(ErrorCode.EXTERNAL_SYNC_FAILED) from exc
        raise
    try:
        kc.execute_actions_email(user_id, ["UPDATE_PASSWORD"])
        status = "email_sent"
    except BusinessException:
        # SMTP is optional in dev: account exists but no email was sent.
        status = "invite_email_unavailable"
    _audit(db, actor, user_id, "invite", None, {"role": data.role, "email_status": status},
           data.name.strip() or None)
    db.commit()
    return _dto({"id": user_id, **payload}, data.role), status


def reset_password(db: Session, kc: KeycloakAdminClient, actor: CurrentUser,
                   user_id: str) -> None:
    target = kc.user(user_id)
    kc.execute_actions_email(user_id, ["UPDATE_PASSWORD"])
    _audit(db, actor, user_id, "password_reset_requested",
           target_name=_target_display_name(target))
    db.commit()
