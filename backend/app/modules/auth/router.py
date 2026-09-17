from fastapi import APIRouter, Depends

from app.core.permissions import require_permission, require_role, user_permissions
from app.core.security import CurrentUser, get_current_user
from app.modules.auth.schemas import MeOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=MeOut)
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


@router.get("/test/authenticated")
def test_authenticated(user: CurrentUser = Depends(get_current_user)):
    return {"ok": True, "user": user.username}


@router.get("/test/admin")
def test_admin(user: CurrentUser = Depends(require_role("admin"))):
    return {"ok": True, "user": user.username}


@router.get("/test/workflow-change")
def test_workflow_change(user: CurrentUser = Depends(require_permission("workflow.change_status"))):
    return {"ok": True, "user": user.username}
