from fastapi import APIRouter, Depends

from app.core.permissions import require_permission, require_role, user_permissions
from app.core.security import CurrentUser, get_current_user
from app.modules.auth.schemas import MeOut
from app.schemas.common import ErrorResponse

router = APIRouter(prefix="/auth", tags=["Auth"])

AUTH_ERRORS = {
    401: {"model": ErrorResponse, "description": "AUTH_REQUIRED — нет/невалиден Bearer токен"},
    403: {"model": ErrorResponse, "description": "FORBIDDEN — нет роли/права"},
}


@router.get(
    "/me",
    response_model=MeOut,
    summary="Текущий пользователь",
    description="Возвращает sub, username, email, роли Keycloak и вычисленные права.",
    responses=AUTH_ERRORS,
)
def me(user: CurrentUser = Depends(get_current_user)):
    perms = user_permissions(user)
    if "*" in perms:
        shown: list[str] = ["*"]
    else:
        shown = sorted(perms)
    return MeOut(
        id=user.id,
        username=user.username,
        email=user.email,
        name=user.name,
        roles=sorted(user.roles),
        permissions=shown,
    )


@router.get(
    "/test/authenticated",
    summary="Проверка аутентификации",
    description="Тестовый endpoint: 200 для любого валидного токена.",
    responses=AUTH_ERRORS,
)
def test_authenticated(user: CurrentUser = Depends(get_current_user)):
    return {"ok": True, "user": user.username}


@router.get(
    "/test/admin",
    summary="Проверка роли admin",
    description="Тестовый endpoint: 200 только для роли admin, иначе 403.",
    responses=AUTH_ERRORS,
)
def test_admin(user: CurrentUser = Depends(require_role("admin"))):
    return {"ok": True, "user": user.username}


@router.get(
    "/test/workflow-change",
    summary="Проверка права workflow.change_status",
    description="Тестовый endpoint: 200 при наличии права, иначе 403.",
    responses=AUTH_ERRORS,
)
def test_workflow_change(user: CurrentUser = Depends(require_permission("workflow.change_status"))):
    return {"ok": True, "user": user.username}
