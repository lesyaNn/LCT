"""University business documents, stored separately from Workflow attachments."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.errors import BusinessException
from app.models.interactions import Document
from app.modules.audit.service import AuditAction, AuditService, context_for
from app.modules.workflow_attachments.policy import (
    MAX_FILE_SIZE_BYTES, UPLOAD_CHUNK_SIZE_BYTES, check_file_type,
    sanitize_filename,
)
from app.modules.workflow_attachments.storage import StorageBackend, new_storage_key
from app.schemas.errors import ErrorCode


def create_document(
    db: Session, storage: StorageBackend, *, university_id: uuid.UUID,
    document_type: str, title: str, filename: str | None,
    content_type: str | None, stream, actor_sub: str,
) -> Document:
    safe_name = sanitize_filename(filename)
    mime_type = check_file_type(safe_name, content_type)
    key = new_storage_key()

    def chunks():
        total = 0
        while chunk := stream.read(UPLOAD_CHUNK_SIZE_BYTES):
            total += len(chunk)
            if total > MAX_FILE_SIZE_BYTES:
                raise BusinessException(ErrorCode.FILE_TOO_LARGE)
            yield chunk

    try:
        size = storage.save_stream(key, chunks())
        document = Document(
            university_id=university_id, document_type=document_type,
            title=title.strip(), file_path=key, file_name=safe_name,
            file_size=size, mime_type=mime_type, status_raw="draft",
            uploaded_by_keycloak_sub=actor_sub,
        )
        db.add(document)
        db.flush()
        AuditService(db).log_event(
            context=context_for(db, actor_sub), action=AuditAction.CREATE,
            entity_type="document", entity_id=document.id,
            university_id=university_id,
            new_value={"document_type": document_type, "title": document.title},
        )
        db.commit()
        db.refresh(document)
        return document
    except Exception:
        db.rollback()
        try:
            storage.delete(key)
        except Exception:
            pass
        raise
