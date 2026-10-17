"""Admin-only user management over the existing Keycloak realm."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.errors import SecurityError
from app.core.permissions import require_permission
from app.core.policies import get_data_scope
from app.core.security import CurrentUser
from app.modules.admin_users import service
from app.modules.admin_users.keycloak_client import KeycloakAdminClient, get_keycloak_admin_client
from app.modules.admin_users.schemas import (
    AdminUserOut, AdminUsersPage, InviteResult, PasswordResetResult,
    UserBlock, UserInvite, UserUpdate,
)
from app.modules.audit.service import get_audit_db
from app.schemas.errors import ErrorCode

router = APIRouter(prefix="/admin/users", tags=["Admin Users"])
ADMIN = require_permission("admin.users")
ASSIGNMENTS = require_permission("user_university.manage")


def live_admin(
    actor: CurrentUser = Depends(ADMIN),
    kc: KeycloakAdminClient = Depends(get_keycloak_admin_client),
) -> CurrentUser:
    """Reject stale admin JWTs immediately after downgrade/block."""
    record = kc.user(actor.id)
    roles = {role.get("name") for role in kc.user_roles(actor.id)}
    if not record.get("enabled", True) or "admin" not in roles:
        raise SecurityError(ErrorCode.FORBIDDEN)
    return actor


def live_user_scope_actor(
    actor: CurrentUser = Depends(ASSIGNMENTS),
    kc: KeycloakAdminClient = Depends(get_keycloak_admin_client),
) -> tuple[CurrentUser, frozenset[UUID] | None]:
    """Use live Keycloak role and scope before any user-assignment read/write."""
    record = kc.user(actor.id)
    roles = {role.get("name") for role in kc.user_roles(actor.id)}
    if not record.get("enabled", True):
        raise SecurityError(ErrorCode.FORBIDDEN)
    if "admin" in (actor.roles or set()) and "admin" in roles:
        return actor, None
    if "manager" in (actor.roles or set()) and "manager" in roles:
        raw = (record.get("attributes") or {}).get("university_ids") or []
        values = raw if isinstance(raw, list) else [raw]
        live = CurrentUser(id=actor.id, roles={"manager"},
                           university_ids=tuple(str(value) for value in values))
        return actor, get_data_scope(live).university_ids
    raise SecurityError(ErrorCode.FORBIDDEN)


@router.get(
    "",
    response_model=AdminUsersPage,
    summary="Список пользователей",
    description="Admin видит всех пользователей; Manager — только доступных ему обычных пользователей и назначения в своей области. Проверяется актуальная роль и область доступа в Keycloak.",
)
def list_admin_users(
    search: str = Query(default="", max_length=256),
    role: Literal["user", "manager", "admin"] | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    access: tuple[CurrentUser, frozenset[UUID] | None] = Depends(live_user_scope_actor),
    kc: KeycloakAdminClient = Depends(get_keycloak_admin_client),
):
    return service.list_users(kc, search=search.strip(), role=role,
                              page=page, page_size=page_size, manager_ids=access[1])


@router.post(
    "/invite",
    response_model=InviteResult,
    status_code=201,
    summary="Пригласить пользователя",
    description="Создаёт/приглашает пользователя в Keycloak по email, имени и ролям. Требуется право admin.users.",
)
def invite_admin_user(
    data: UserInvite, actor: CurrentUser = Depends(live_admin),
    db: Session = Depends(get_audit_db),
    kc: KeycloakAdminClient = Depends(get_keycloak_admin_client),
):
    user, status = service.invite_user(db, kc, actor, data)
    return InviteResult(user=user, status=status)


@router.get(
    "/{user_id}",
    response_model=AdminUserOut,
    summary="Карточка пользователя",
    description="Admin видит любого пользователя; Manager — только обычного пользователя в своей области.",
)
def get_admin_user(
    user_id: UUID, access: tuple[CurrentUser, frozenset[UUID] | None] = Depends(live_user_scope_actor),
    kc: KeycloakAdminClient = Depends(get_keycloak_admin_client),
):
    return service.get_user(kc, str(user_id), manager_ids=access[1])


@router.patch(
    "/{user_id}",
    response_model=AdminUserOut,
    summary="Обновить пользователя",
    description="Admin меняет роль и вузы; Manager меняет только назначения обычного пользователя в своей области.",
)
def update_admin_user(
    user_id: UUID, change: UserUpdate,
    access: tuple[CurrentUser, frozenset[UUID] | None] = Depends(live_user_scope_actor),
    db: Session = Depends(get_audit_db),
    kc: KeycloakAdminClient = Depends(get_keycloak_admin_client),
):
    return service.update_user(db, kc, access[0], str(user_id), change, manager_ids=access[1])


@router.post(
    "/{user_id}/block",
    response_model=AdminUserOut,
    summary="Заблокировать/разблокировать пользователя",
    description="Включает или отключает учётную запись (флаг blocked в теле запроса). Требуется право admin.users.",
)
def block_admin_user(
    user_id: UUID, change: UserBlock, actor: CurrentUser = Depends(live_admin),
    db: Session = Depends(get_audit_db),
    kc: KeycloakAdminClient = Depends(get_keycloak_admin_client),
):
    return service.set_blocked(db, kc, actor, str(user_id), change.blocked)


@router.post(
    "/{user_id}/password-reset",
    response_model=PasswordResetResult,
    summary="Сбросить пароль пользователя",
    description="Инициирует сброс пароля пользователя в Keycloak. Требуется право admin.users.",
)
def reset_admin_user_password(
    user_id: UUID, actor: CurrentUser = Depends(live_admin),
    db: Session = Depends(get_audit_db),
    kc: KeycloakAdminClient = Depends(get_keycloak_admin_client),
):
    service.reset_password(db, kc, actor, str(user_id))
    return PasswordResetResult()
