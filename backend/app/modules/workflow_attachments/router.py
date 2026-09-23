"""P2-05 HTTP API (mounted under /api/v1/workflow).

Thin routes: params -> frozen RBAC -> instance access chain -> service.
No SQL here. Upload streams in chunks (never ``await file.read()``
whole-file); the original filename travels as metadata only.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.core.security import CurrentUser
from app.db.session import get_db
from app.modules.workflow_attachments import service
from app.modules.workflow_attachments.policy import (
    UPLOAD_CHUNK_SIZE_BYTES,
    content_disposition,
)
from app.modules.workflow_attachments.schemas import AttachmentRead
from app.modules.workflow_attachments.storage import (
    StorageBackend,
    build_storage_backend,
)
from app.schemas.common import PaginatedResponse

router = APIRouter(prefix="/workflow", tags=["Workflow"])

READ = require_permission("workflow.read")
WRITE = require_permission("workflow.change_status")


def get_storage() -> StorageBackend:
    """Production storage (overridable in tests via dependency_overrides)."""
    return build_storage_backend()


@router.post(
    "/instances/{instance_id}/attachments",
    response_model=AttachmentRead,
    status_code=201,
    summary="Upload a file to a workflow instance (streamed, max 50 MiB)",
)
def upload_attachment(
    instance_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
    user: CurrentUser = Depends(WRITE),
) -> AttachmentRead:
    instance = service.get_instance_or_404(db, instance_id)
    service.authorize_scope(user, instance)
    attachment = service.upload_attachment(
        db,
        storage,
        instance_id=instance.id,
        filename=file.filename,
        content_type=file.content_type,
        stream=file.file,
        actor_sub=user.id,
    )
    return AttachmentRead.model_validate(attachment)


@router.get(
    "/instances/{instance_id}/attachments",
    response_model=PaginatedResponse[AttachmentRead],
    summary="List attachment metadata for an instance (oldest first)",
)
def list_attachments(
    instance_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(READ),
) -> PaginatedResponse[AttachmentRead]:
    instance = service.get_instance_or_404(db, instance_id)
    service.authorize_scope(user, instance)
    rows, total = service.list_attachments(db, instance.id, page=page, page_size=page_size)
    return PaginatedResponse(
        items=[AttachmentRead.model_validate(r) for r in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/instances/{instance_id}/attachments/{attachment_id}",
    response_model=AttachmentRead,
    summary="Get attachment metadata (no storage paths leaked)",
)
def get_attachment_metadata(
    instance_id: uuid.UUID,
    attachment_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(READ),
) -> AttachmentRead:
    instance = service.get_instance_or_404(db, instance_id)
    service.authorize_scope(user, instance)
    attachment = service.get_bound_attachment(
        db, instance_id=instance.id, attachment_id=attachment_id
    )
    return AttachmentRead.model_validate(attachment)


@router.get(
    "/instances/{instance_id}/attachments/{attachment_id}/download",
    summary="Download attachment bytes (streamed)",
    response_class=StreamingResponse,
)
def download_attachment(
    instance_id: uuid.UUID,
    attachment_id: uuid.UUID,
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
    user: CurrentUser = Depends(READ),
) -> StreamingResponse:
    instance = service.get_instance_or_404(db, instance_id)
    service.authorize_scope(user, instance)
    attachment = service.get_bound_attachment(
        db, instance_id=instance.id, attachment_id=attachment_id
    )
    _, opener, handle = service.open_download(db, storage, attachment=attachment)
    mime = attachment.mime_type or "application/octet-stream"

    def _iter():
        try:
            while True:
                chunk = handle.read(UPLOAD_CHUNK_SIZE_BYTES)
                if not chunk:
                    break
                yield chunk
        finally:
            opener.__exit__(None, None, None)

    return StreamingResponse(
        _iter(),
        media_type=mime,
        headers={
            "Content-Length": str(attachment.file_size),
            "Content-Disposition": content_disposition(attachment.original_filename),
        },
    )


@router.delete(
    "/instances/{instance_id}/attachments/{attachment_id}",
    status_code=204,
    summary="Delete attachment object and metadata",
)
def delete_attachment(
    instance_id: uuid.UUID,
    attachment_id: uuid.UUID,
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
    user: CurrentUser = Depends(WRITE),
):
    instance = service.get_instance_or_404(db, instance_id)
    service.authorize_scope(user, instance)
    attachment = service.get_bound_attachment(
        db, instance_id=instance.id, attachment_id=attachment_id
    )
    service.delete_attachment(db, storage, attachment=attachment)
    return None
