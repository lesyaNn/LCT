"""File operations for the canonical Contract entity."""

import uuid

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.models.catalog import Contract
from app.modules.workflow_attachments.policy import (
    MAX_FILE_SIZE_BYTES, UPLOAD_CHUNK_SIZE_BYTES, check_file_type, sanitize_filename,
)
from app.modules.workflow_attachments.storage import StorageBackend, new_storage_key


def contract_or_404(db: Session, contract_id: uuid.UUID) -> Contract:
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    return contract


def attach_contract_file(db: Session, storage: StorageBackend, contract: Contract, file: UploadFile) -> Contract:
    name = sanitize_filename(file.filename)
    mime = check_file_type(name, file.content_type)
    key = new_storage_key()
    old_key = contract.file_path

    def chunks():
        size = 0
        while chunk := file.file.read(UPLOAD_CHUNK_SIZE_BYTES):
            size += len(chunk)
            if size > MAX_FILE_SIZE_BYTES:
                raise HTTPException(status_code=413, detail="File too large")
            yield chunk

    try:
        size = storage.save_stream(key, chunks())
        contract.file_path = key
        contract.file_name = name
        contract.file_size = size
        contract.file_mime_type = mime
        db.commit()
        db.refresh(contract)
    except Exception:
        db.rollback()
        try:
            storage.delete(key)
        except Exception:
            pass
        raise
    if old_key:
        try:
            storage.delete(old_key)
        except Exception:
            pass
    return contract


def detach_contract_file(db: Session, storage: StorageBackend, contract: Contract) -> None:
    key = contract.file_path
    if not key:
        raise HTTPException(status_code=404, detail="Contract file not found")
    contract.file_path = None
    contract.file_name = None
    contract.file_size = None
    contract.file_mime_type = None
    db.commit()
    try:
        storage.delete(key)
    except Exception:
        pass
