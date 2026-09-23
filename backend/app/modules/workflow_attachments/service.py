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

import uuid
from typing import BinaryIO

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFound
from app.core.permissions import user_permissions
from app.models.workflow_instances import WorkflowAttachment, WorkflowInstance

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


def get_instance_or_404(db: Session, instance_id: uuid.UUID) -> WorkflowInstance:
    instance = db.get(WorkflowInstance, instance_id)
    if instance is None:
        raise NotFound("Workflow instance not found")
    return instance


def authorize_scope(user, instance: WorkflowInstance) -> None:
    """University-scope gate for one instance (permission checked by router).

    Admins (``*``) skip scoping; other roles are confined to
    ``user.university_ids`` when the token carries that optional claim.
    Tokens without the claim keep the pre-existing global RBAC behaviour.
    """
    perms = user_permissions(user)
    if "*" in perms:
        return
    scope = getattr(user, "university_ids", None)
    if scope is not None and str(instance.university_id) not in set(scope):
        raise HTTPException(status_code=403, detail="Forbidden: other university")


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
            raise HTTPException(status_code=413, detail="File too large (limit 50 MiB)")
        yield piece


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
    instance = get_instance_or_404(db, instance_id)
    safe_name = sanitize_filename(filename)
    mime = check_file_type(safe_name, content_type)
    key = new_storage_key()
    try:
        size = storage.save_stream(key, _limited_chunks(stream))
    except HTTPException:
        raise
    except StorageError as exc:
        raise HTTPException(status_code=500, detail="File storage unavailable") from exc
    attachment = WorkflowAttachment(
        instance_id=instance.id,
        original_filename=safe_name,
        storage_key=key,
        file_size=size,
        mime_type=mime,
        uploaded_by_keycloak_sub=actor_sub or "",
    )
    db.add(attachment)
    try:
        db.commit()
    except Exception:
        db.rollback()
        try:
            storage.delete(key)
        except StorageError:
            pass
        raise
    db.refresh(attachment)
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
        raise HTTPException(status_code=500, detail="File storage unavailable") from exc
    return attachment, opener, handle


def delete_attachment(
    db: Session, storage: StorageBackend, *, attachment: WorkflowAttachment
) -> None:
    """Physical object first, metadata row second (no false 204)."""
    try:
        storage.delete(attachment.storage_key)
    except StorageObjectNotFound:
        pass  # idempotent: row cleanup below still happens
    except StorageError as exc:
        raise HTTPException(status_code=500, detail="File storage unavailable") from exc
    db.delete(attachment)
    db.commit()
