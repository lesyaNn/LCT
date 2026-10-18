"""P1-04-01/05/06: GET /api/v1/universities/{id}/passport + subresources.

Thin routes: params -> auth/RBAC -> service -> DTO. No SQL, no business
logic here (architecture rule API -> Service -> Model/Repository).
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.openapi import file_response
from app.modules.workflow_attachments.preview_schemas import FilePreview
from app.db.session import get_db
from app.modules.audit.service import get_audit_db
from app.core.permissions import require_permission
from app.core.policies import ensure_university_access
from app.core.security import CurrentUser
from app.modules.universities.passport_schemas import (
    DocumentShort,
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
from app.schemas.common import DocumentType
from app.modules.universities.document_service import create_document
from app.modules.universities.passport_blocks import document_to_short

router = APIRouter(prefix="/universities", tags=["universities-passport"])


@router.get("/{university_id}/history", summary="История вуза",
    description="Возвращает человекочитаемую историю вуза (события и документы). Требуется право university.read.")
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
    summary="Паспорт вуза",
    description="Возвращает агрегированный цифровой паспорт вуза; параметр include подключает блок audit. Требуется право university.read.",
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
    summary="Программы паспорта вуза",
    description="Возвращает страницу программ вуза с фильтром по статусу. Требуется право university.read.",
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
    summary="Документы паспорта вуза",
    description="Возвращает страницу документов вуза с поиском и фильтрами по типу и статусу. Требуется право university.read.",
)
def get_university_passport_documents(
    university_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = None,
    document_type: str | None = None,
    status: str | None = None,
    document_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission("university.read")),
) -> PaginatedDocuments:
    ensure_university_access(university_id, user)
    items, total, types = get_documents_page(
        db, university_id, page, page_size,
        search=search, document_type=document_type, status=status, document_id=document_id,
    )
    return PaginatedDocuments(items=items, page=page, page_size=page_size, total=total, types=types)


@router.post(
    "/{university_id}/passport/documents",
    response_model=DocumentShort,
    status_code=201,
    summary="Загрузить документ вуза",
    description="Загружает деловой документ вуза (тип, заголовок и файл). Требуется право university.edit.",
)
def upload_university_document(
    university_id: uuid.UUID,
    document_type: DocumentType = Form(...),
    title: str = Form(min_length=1, max_length=1024),
    file: UploadFile = File(...),
    db: Session = Depends(get_audit_db),
    storage: StorageBackend = Depends(get_storage),
    user: CurrentUser = Depends(require_permission("university.edit")),
) -> DocumentShort:
    ensure_university_access(university_id, user)
    document = create_document(
        db, storage, university_id=university_id,
        document_type=document_type.value, title=title,
        filename=file.filename, content_type=file.content_type,
        stream=file.file, actor_sub=user.id,
    )
    return document_to_short(document)


@router.get(
    "/{university_id}/passport/documents/{document_id}/download",
    response_class=FileResponse,
    responses={200: file_response("Документ; Content-Type соответствует формату файла")},
    summary="Скачать документ вуза",
    description="Скачивает файл документа вуза с проверкой доступа. Требуется право university.read.",
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


@router.get("/{university_id}/passport/documents/{document_id}/preview",
            response_model=FilePreview, responses={503: {"description": "Предпросмотр или хранилище недоступны"}}, summary="Предпросмотр документа вуза")
def preview_university_document(
    university_id: uuid.UUID, document_id: uuid.UUID,
    offset: int = Query(default=0, ge=0, le=9900),
    db: Session = Depends(get_db), storage: StorageBackend = Depends(get_storage),
    user: CurrentUser = Depends(require_permission("university.read")),
):
    from app.modules.workflow_attachments.preview import preview_response
    ensure_university_access(university_id, user)
    document = db.get(Document, document_id)
    if document is None or document.university_id != university_id or not document.file_path:
        raise HTTPException(404, "Document not found")
    path = document_storage_path(document.file_path)
    if path is not None:
        return preview_response(storage, document.file_path, document.file_name or "document", offset,
                                source_factory=lambda: path.open("rb"))
    return preview_response(storage, document.file_path, document.file_name or "document", offset)
