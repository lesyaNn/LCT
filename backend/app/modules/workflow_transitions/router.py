"""P2-03/P2-04 HTTP API (mounted under /api/v1/workflow).

Thin routes: params -> frozen RBAC -> university scope -> service -> DTO.
No SQL here.

RBAC (frozen permission names, same as the B1 instance/attachment gates):
* ``GET`` history/comments need ``workflow.read``;
* ``POST``/``PATCH`` mutations need ``workflow.change_status``;
* comment edits additionally enforce author-or-admin inside the service
  (``require_role("admin")`` is NOT a route gate here so authors keep their
  15-minute window).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.core.security import CurrentUser
from app.modules.audit.service import get_audit_db
from app.modules.audit.workflow_actor_names import workflow_actor_names
from app.modules.workflow_instances import service as instance_service
from app.modules.admin_users.keycloak_client import KeycloakAdminClient, get_keycloak_admin_client
from app.modules.notifications.workflow_comments import notify_comment
from app.modules.workflow_attachments.router import get_storage
from app.modules.workflow_attachments.storage import StorageBackend
from app.modules.workflow_instances.schemas import AllowedTransitionRead, InstanceDetail
from app.modules.workflow_transitions import service
from app.modules.workflow_transitions.schemas import (
    TransitionRequest,
    WorkflowCommentCreate,
    WorkflowCommentRead,
    WorkflowCommentUpdate,
    WorkflowStageTransitionRead,
)
from app.schemas.common import PaginatedResponse

router = APIRouter(prefix="/workflow", tags=["Workflow"])

READ = require_permission("workflow.read")
WRITE = require_permission("workflow.change_status")


@router.post(
    "/instances/{instance_id}/comments/with-attachments",
    response_model=WorkflowCommentRead,
    status_code=201,
    summary="Комментарий с вложениями",
    description="Создаёт комментарий экземпляра вместе с вложениями (1–10 файлов) атомарно. Требуемое право: workflow.change_status.",
)
def add_comment_with_attachments(
    instance_id: uuid.UUID,
    content: str = Form(..., min_length=1, max_length=10000),
    is_question: bool = Form(False),
    stage_id: uuid.UUID | None = Form(None),
    files: list[UploadFile] = File(..., min_length=1, max_length=10),
    db: Session = Depends(get_audit_db),
    storage: StorageBackend = Depends(get_storage),
    user: CurrentUser = Depends(WRITE),
    kc: KeycloakAdminClient = Depends(get_keycloak_admin_client),
) -> WorkflowCommentRead:
    instance = service.get_instance_or_404(db, instance_id)
    instance_service.authorize_scope(user, instance)
    comment = service.add_comment_with_files(
        db, storage, instance_id,
        WorkflowCommentCreate(content=content, stage_id=stage_id, is_question=is_question), files, user.id,
    )
    notify_comment(db, kc, instance, comment, user)
    return WorkflowCommentRead.model_validate(comment)


@router.post(
    "/instances/{instance_id}/transition",
    response_model=InstanceDetail,
    summary="Переход экземпляра на этап",
    description="Переводит экземпляр workflow на более поздний этап атомарно, опционально с комментарием. Требуемое право: workflow.change_status.",
)
def transition_instance(
    instance_id: uuid.UUID,
    data: TransitionRequest,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(WRITE),
) -> InstanceDetail:
    existing = service.get_instance_or_404(db, instance_id)
    instance_service.authorize_scope(user, existing)
    instance = service.transition_instance(
        db,
        instance_id,
        data.target_instance_stage_id,
        data.comment,
        user.id,
    )
    return instance_service.get_instance_detail(db, instance.id)


@router.post(
    "/instances/{instance_id}/complete",
    response_model=InstanceDetail,
    summary="Завершение экземпляра",
    description="Атомарно завершает финальный этап и весь экземпляр workflow. Требуемое право: workflow.change_status.",
)
def complete_instance(
    instance_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(WRITE),
) -> InstanceDetail:
    existing = service.get_instance_or_404(db, instance_id)
    instance_service.authorize_scope(user, existing)
    instance = service.complete_instance(db, instance_id, user.id)
    return instance_service.get_instance_detail(db, instance.id)


@router.get(
    "/instances/{instance_id}/rollback-targets",
    response_model=list[AllowedTransitionRead],
    summary="Цели отката экземпляра",
    description="Возвращает предыдущие закрытые этапы, на которые можно откатить экземпляр (сначала новые). Требуемое право: workflow.read.",
)
def list_rollback_targets(
    instance_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(READ),
) -> list[AllowedTransitionRead]:
    existing = service.get_instance_or_404(db, instance_id)
    instance_service.authorize_scope(user, existing)
    stages = service.ordered_stages(instance_id, db)
    return [
        AllowedTransitionRead(id=row.id, order_index=row.order_index, name=row.name)
        for row in service.rollback_targets(existing, stages)
    ]


@router.post(
    "/instances/{instance_id}/rollback",
    response_model=InstanceDetail,
    summary="Откат экземпляра на этап",
    description="Возвращает экземпляр workflow на предыдущий этап атомарно, опционально с комментарием. Требуемое право: workflow.change_status.",
)
def rollback_instance(
    instance_id: uuid.UUID,
    data: TransitionRequest,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(WRITE),
) -> InstanceDetail:
    existing = service.get_instance_or_404(db, instance_id)
    instance_service.authorize_scope(user, existing)
    instance = service.rollback_instance(
        db,
        instance_id,
        data.target_instance_stage_id,
        data.comment,
        user.id,
    )
    return instance_service.get_instance_detail(db, instance.id)


@router.get(
    "/instances/{instance_id}/transitions",
    response_model=list[WorkflowStageTransitionRead],
    summary="История переходов экземпляра",
    description="Возвращает историю переходов экземпляра: предыдущий и новый этапы, автор и комментарий. Требуемое право: workflow.read.",
)
def list_transitions(
    instance_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(READ),
) -> list[WorkflowStageTransitionRead]:
    instance = service.get_instance_or_404(db, instance_id)
    instance_service.authorize_scope(user, instance)
    return service.list_transitions(db, instance_id)


@router.get(
    "/instances/{instance_id}/comments",
    response_model=PaginatedResponse[WorkflowCommentRead],
    summary="Список комментариев экземпляра",
    description="Возвращает постраничный список комментариев экземпляра, сначала старые. Требуемое право: workflow.read.",
)
def list_comments(
    instance_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(READ),
) -> PaginatedResponse[WorkflowCommentRead]:
    instance = service.get_instance_or_404(db, instance_id)
    instance_service.authorize_scope(user, instance)
    rows, total = service.list_comment_page(db, instance_id, page=page, page_size=page_size)
    names = workflow_actor_names(db, "workflow_comment", [row.id for row in rows])
    return PaginatedResponse(
        items=[WorkflowCommentRead.model_validate(r).model_copy(update={"author_name": names.get(r.id)}) for r in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post(
    "/instances/{instance_id}/comments",
    response_model=WorkflowCommentRead,
    status_code=201,
    summary="Добавление комментария",
    description="Добавляет комментарий к экземпляру workflow, опционально с привязкой к этапу. Требуемое право: workflow.change_status.",
)
def add_comment(
    instance_id: uuid.UUID,
    data: WorkflowCommentCreate,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(WRITE),
    kc: KeycloakAdminClient = Depends(get_keycloak_admin_client),
) -> WorkflowCommentRead:
    instance = service.get_instance_or_404(db, instance_id)
    instance_service.authorize_scope(user, instance)
    comment = service.add_comment(db, instance_id, data, user.id)
    notify_comment(db, kc, instance, comment, user)
    return comment


@router.patch(
    "/comments/{comment_id}",
    response_model=WorkflowCommentRead,
    summary="Редактирование комментария",
    description="Редактирует комментарий workflow: автор — в течение 15 минут, admin — в любое время. Требуемое право: workflow.change_status.",
)
def edit_comment(
    comment_id: uuid.UUID,
    data: WorkflowCommentUpdate,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(WRITE),
) -> WorkflowCommentRead:
    existing = service.get_comment_or_404(db, comment_id)
    instance = service.get_instance_or_404(db, existing.instance_id)
    instance_service.authorize_scope(user, instance)
    comment = service.edit_comment(
        db, comment_id, data, user.id, set(user.roles or ())
    )
    return comment


@router.delete(
    "/comments/{comment_id}",
    status_code=204,
    response_model=None,
    summary="Удаление комментария",
    description="Удаляет комментарий workflow: автор — в течение 15 минут, admin — в любое время. Требуемое право: workflow.change_status.",
)
def delete_comment(
    comment_id: uuid.UUID,
    db: Session = Depends(get_audit_db),
    user: CurrentUser = Depends(WRITE),
) -> None:
    existing = service.get_comment_or_404(db, comment_id)
    instance = service.get_instance_or_404(db, existing.instance_id)
    instance_service.authorize_scope(user, instance)
    service.delete_comment(db, comment_id, user.id, set(user.roles or ()))
