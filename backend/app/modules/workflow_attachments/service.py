"""P2-05 attachment service: instance-bound metadata + streamed objects.

Canonical access chain (never UUID-only)::

    workflow_attachment -> workflow_instance -> university

Every operation resolves the instance first (404 when missing), binds the
attachment row to the URL instance (404 on cross-instance/cross-university
addressing), then enforces frozen RBAC plus the optional JWT university
scope. Storage IO goes only through :class:`StorageBackend`.

Failure semantics:

* oversize (``> 50 MiB``) -> 413, no metadata row, no final/temp file;
* DB failure after the physical write -> the object is removed;
* delete: physical object first, metadata row second; a storage failure
  keeps the row and never yields a false 204; an already-missing object
  still removes the row (idempotent delete -> 204).
"""

from __future__ import annotations

import logging
import uuid
from typing import BinaryIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFound
from app.core.errors import BusinessException
from app.schemas.errors import ErrorCode
from app.core.policies import ensure_university_access
from app.models.workflow_instances import WorkflowAttachment, WorkflowInstance
from app.modules.workflow_instances.service import get_instance_or_404

logger = logging.getLogger(__name__)

from .policy import (
    MAX_FILE_SIZE_BYTES,
    UPLOAD_CHUNK_SIZE_BYTES,
    check_file_type,
    sanitize_filename,
)
from .storage import (
    StorageBackend,
    StorageError,
    StorageObjectNotFound,
    new_storage_key,
)


def authorize_scope(user, instance: WorkflowInstance) -> None:
    """Compatibility adapter for existing P2 call sites."""
    ensure_university_access(instance.university_id, user)


def get_bound_attachment(
    db: Session, *, instance_id: uuid.UUID, attachment_id: uuid.UUID
) -> WorkflowAttachment:
    """Instance row + attachment row bound to it (cross-instance -> 404)."""
    get_instance_or_404(db, instance_id)
    attachment = db.get(WorkflowAttachment, attachment_id)
    if attachment is None or attachment.instance_id != instance_id:
        raise NotFound("Attachment not found")
    return attachment


def list_attachments(
    db: Session, instance_id: uuid.UUID, *, page: int, page_size: int
) -> tuple[list[WorkflowAttachment], int]:
    """Attachment metadata for one instance, oldest first (P2-05-02)."""
    get_instance_or_404(db, instance_id)
    base = select(WorkflowAttachment).where(
        WorkflowAttachment.instance_id == instance_id
    )
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(
            base.order_by(
                WorkflowAttachment.created_at.asc(), WorkflowAttachment.id.asc()
            )
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        .scalars()
        .all()
    )
    return list(rows), total


def _limited_chunks(stream: BinaryIO):
    """Sync chunk generator with the hard 50 MiB cap (413 mid-stream)."""
    total = 0
    while True:
        piece = stream.read(UPLOAD_CHUNK_SIZE_BYTES)
        if not piece:
            return
        total += len(piece)
        if total > MAX_FILE_SIZE_BYTES:
            raise BusinessException(ErrorCode.FILE_TOO_LARGE)
        yield piece


def _audit_attachment_event(db: Session, *, action: str, attachment: WorkflowAttachment,
                              university_id) -> None:
    """H3: upload/delete пишут аудит в той же транзакции; без audit_context
    (воркер/прямые вызовы) — молча пропускаем, как остальные сервисы."""
    if "audit_context" not in db.info:
        return
    from app.modules.audit.service import AuditService, context_for

    snapshot = {
        "audit_object_type": "workflow_attachment",
        "instance_id": str(attachment.instance_id),
        "comment_id": str(attachment.comment_id) if attachment.comment_id else None,
        "original_filename": attachment.original_filename,
        "file_size": attachment.file_size,
        "mime_type": attachment.mime_type,
    }
    try:
        from app.models.workflow_instances import WorkflowInstance
        from app.models.workflow_templates import WorkflowTemplate

        instance = db.get(WorkflowInstance, attachment.instance_id)
        if instance is not None:
            if university_id is None:
                university_id = instance.university_id
            if instance.template_id is not None:
                template = db.get(WorkflowTemplate, instance.template_id)
                if template is not None and template.name:
                    snapshot["template_name"] = template.name
    except Exception:
        pass
    AuditService(db).log_event(
        context=context_for(db, attachment.uploaded_by_keycloak_sub or "system"),
        action=action,
        entity_type="document",
        entity_id=attachment.id,
        university_id=university_id,
        old_value=None if action == "CREATE" else snapshot,
        new_value=snapshot if action == "CREATE" else None,
    )


def upload_attachment(
    db: Session,
    storage: StorageBackend,
    *,
    instance_id: uuid.UUID,
    filename: str | None,
    content_type: str | None,
    stream: BinaryIO,
    actor_sub: str,
) -> WorkflowAttachment:
    """Stream an upload to storage, then record canonical metadata."""
    attachment = stage_attachment(
        db, storage, instance_id=instance_id, filename=filename,
        content_type=content_type, stream=stream, actor_sub=actor_sub,
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        try:
            storage.delete(attachment.storage_key)
        except StorageError:
            logger.exception("attachment storage cleanup failed", extra={"key": attachment.storage_key})
        raise
    db.refresh(attachment)
    return attachment


def stage_attachment(
    db: Session, storage: StorageBackend, *, instance_id: uuid.UUID,
    filename: str | None, content_type: str | None, stream: BinaryIO,
    actor_sub: str, comment_id: uuid.UUID | None = None,
) -> WorkflowAttachment:
    """Store one object and stage its metadata in the caller's transaction."""
    instance = get_instance_or_404(db, instance_id)
    safe_name = sanitize_filename(filename)
    mime = check_file_type(safe_name, content_type)
    key = new_storage_key()
    try:
        size = storage.save_stream(key, _limited_chunks(stream))
    except BusinessException:
        raise
    except StorageError as exc:
        raise BusinessException(ErrorCode.INTERNAL_ERROR) from exc
    attachment = WorkflowAttachment(
        instance_id=instance.id,
        comment_id=comment_id,
        original_filename=safe_name,
        storage_key=key,
        file_size=size,
        mime_type=mime,
        uploaded_by_keycloak_sub=actor_sub or "",
    )
    db.add(attachment)
    try:
        if "audit_context" in db.info:
            db.flush()  # Generate attachment.id before the same-transaction audit event.
        _audit_attachment_event(
            db, action="CREATE", attachment=attachment,
            university_id=instance.university_id,
        )
    except Exception:
        db.rollback()
        try:
            storage.delete(key)
        except StorageError:
            logger.exception("attachment storage cleanup failed", extra={"key": key})
        raise
    return attachment


def open_download(db: Session, storage: StorageBackend, *, attachment: WorkflowAttachment):
    """Authorize-first download handle; missing object -> 404 (P2-05-02)."""
    _ = db  # metadata already resolved by the caller via get_bound_attachment
    try:
        opener = storage.open_stream(attachment.storage_key)
        handle = opener.__enter__()
    except StorageObjectNotFound:
        raise NotFound("Attachment file not found") from None
    except StorageError as exc:
        raise BusinessException(ErrorCode.INTERNAL_ERROR) from exc
    return attachment, opener, handle


def delete_attachment(
    db: Session, storage: StorageBackend, *, attachment: WorkflowAttachment
) -> None:
    """Physical object first, metadata row second (no false 204)."""
    instance = get_instance_or_404(db, attachment.instance_id)
    try:
        storage.delete(attachment.storage_key)
    except StorageObjectNotFound:
        pass  # idempotent: row cleanup below still happens
    except StorageError as exc:
        raise BusinessException(ErrorCode.INTERNAL_ERROR) from exc
    _audit_attachment_event(
        db, action="DELETE", attachment=attachment,
        university_id=instance.university_id,
    )
    db.delete(attachment)
    db.commit()
