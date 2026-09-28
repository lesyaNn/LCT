"""P1-04-01/05/06: GET /api/v1/universities/{id}/passport + subresources.

Thin routes: params -> auth/RBAC -> service -> DTO. No SQL, no business
logic here (architecture rule API -> Service -> Model/Repository).
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.permissions import require_permission
from app.core.policies import ensure_university_access
from app.core.security import CurrentUser
from app.modules.universities.passport_schemas import (
    PaginatedDocuments,
    PaginatedPrograms,
    UniversityPassport,
)
from app.modules.universities.passport_service import (
    get_passport,
    get_documents_page,
    document_storage_path,
    get_programs_page,
    parse_include,
)
from app.modules.universities.history_service import university_history
from app.modules.workflow_attachments.router import get_storage
from app.modules.workflow_attachments.storage import StorageBackend
from app.models.interactions import Document

router = APIRouter(prefix="/universities", tags=["universities-passport"])


@router.get("/{university_id}/history", summary="Human-readable history of one university")
def get_university_history(
    university_id: uuid.UUID,
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
    user: CurrentUser = Depends(require_permission("university.read")),
) -> list[dict]:
    ensure_university_access(university_id, user)
    return university_history(db, university_id, storage)


@router.get(
    "/{university_id}/passport",
    response_model=UniversityPassport,
    summary="University digital passport (aggregated)",
)
def get_university_passport(
    university_id: uuid.UUID,
    include: str | None = Query(
        default=None,
        description="Optional blocks, comma-separated: audit",
    ),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("university.read")),
) -> UniversityPassport:
    ensure_university_access(university_id, user)
    blocks = parse_include(include)
    return get_passport(db, university_id, include=blocks)


@router.get(
    "/{university_id}/passport/programs",
    response_model=PaginatedPrograms,
    summary="University passport programs (paginated)",
)
def get_university_passport_programs(
    university_id: uuid.UUID,
    page: int = Query(default=1, ge=1, description="Page number, 1-based"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status: Literal["planned", "active", "launched", "archived"] | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("university.read")),
) -> PaginatedPrograms:
    ensure_university_access(university_id, user)
    items, total = get_programs_page(db, university_id, page, page_size, status=status)
    return PaginatedPrograms(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/{university_id}/passport/documents",
    response_model=PaginatedDocuments,
    summary="University documents with server-side filters and pagination",
)
def get_university_passport_documents(
    university_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = None,
    document_type: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("university.read")),
) -> PaginatedDocuments:
    ensure_university_access(university_id, user)
    items, total, types = get_documents_page(
        db, university_id, page, page_size,
        search=search, document_type=document_type, status=status,
    )
    return PaginatedDocuments(items=items, page=page, page_size=page_size, total=total, types=types)


@router.get(
    "/{university_id}/passport/documents/{document_id}/download",
    summary="Download a university document with authentication and scope checks",
)
def download_university_document(
    university_id: uuid.UUID,
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("university.read")),
) -> FileResponse:
    ensure_university_access(university_id, user)
    document = db.get(Document, document_id)
    if document is None or document.university_id != university_id:
        raise HTTPException(status_code=404, detail="Document not found")
    path = document_storage_path(document.file_path)
    if path is None:
        raise HTTPException(status_code=404, detail="Document file unavailable")
    return FileResponse(path, media_type=document.mime_type or "application/octet-stream", filename=document.file_name)
