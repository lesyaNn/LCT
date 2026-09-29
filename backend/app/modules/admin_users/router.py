"""Admin-only user management over the existing Keycloak realm."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.errors import SecurityError
from app.core.permissions import require_permission
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


@router.get(
    "",
    response_model=AdminUsersPage,
    summary="Список пользователей",
    description="Возвращает постраничный список пользователей Keycloak с поиском по строке и фильтром по роли. Требуется право admin.users (проверка live_admin).",
)
def list_admin_users(
    search: str = Query(default="", max_length=256),
    role: Literal["user", "manager", "admin"] | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _actor: CurrentUser = Depends(live_admin),
    kc: KeycloakAdminClient = Depends(get_keycloak_admin_client),
):
    return service.list_users(kc, search=search.strip(), role=role,
                              page=page, page_size=page_size)


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
    description="Возвращает одного пользователя по UUID из Keycloak. Требуется право admin.users.",
)
def get_admin_user(
    user_id: UUID, _actor: CurrentUser = Depends(live_admin),
    kc: KeycloakAdminClient = Depends(get_keycloak_admin_client),
):
    return service.get_user(kc, str(user_id))


@router.patch(
    "/{user_id}",
    response_model=AdminUserOut,
    summary="Обновить пользователя",
    description="Обновляет имя, email и роли пользователя в Keycloak. Требуется право admin.users.",
)
def update_admin_user(
    user_id: UUID, change: UserUpdate, actor: CurrentUser = Depends(live_admin),
    db: Session = Depends(get_audit_db),
    kc: KeycloakAdminClient = Depends(get_keycloak_admin_client),
):
    return service.update_user(db, kc, actor, str(user_id), change)


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
