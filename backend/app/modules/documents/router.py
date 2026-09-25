"""LEGACY QUARANTINE (M7) — DO NOT MOUNT in ``app/api/router.py``.

Reactivation requires the checklist in ``docs/AUDIT.md`` (§0): service
layer, UUID identities, ``PaginatedResponse``, RBAC + data-scope, audit.
Direct ``db.query``/``db.commit`` in handlers below is the reason this
router stays unmounted (see ``scripts/check_legacy_quarantine.py``).
"""

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import CurrentUser, get_current_user
from app.core.errors import BusinessException
from app.schemas.errors import ErrorCode
from app.db.session import get_db
from app.infrastructure import storage
from app.modules.documents.models import FileMeta

ALLOWED = {"application/pdf", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
           "text/csv", "application/msword",
           "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
           "image/png", "image/jpeg"}

router = APIRouter(prefix="/documents", tags=["documents"])


class FileOut(BaseModel):
    id: int
    original_filename: str
    storage_key: str
    content_type: str
    size: int
    entity_type: str
    entity_id: int

    model_config = {"from_attributes": True}


@router.post("/upload", response_model=FileOut, status_code=201)
async def upload(entity_type: str = "university", entity_id: int = 0,
                 f: UploadFile = File(...), db: Session = Depends(get_db),
                 user: CurrentUser = Depends(get_current_user)):
    content = await f.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise BusinessException(ErrorCode.FILE_TOO_LARGE)
    if f.content_type and f.content_type not in ALLOWED:
        raise BusinessException(ErrorCode.FILE_TYPE_NOT_ALLOWED)
    key = storage.save_file(f.filename or "file", content)
    meta = FileMeta(original_filename=f.filename or "file", storage_key=key,
                    content_type=f.content_type or "", size=len(content),
                    uploaded_by=user.id, entity_type=entity_type, entity_id=entity_id)
    db.add(meta)
    db.commit()
    db.refresh(meta)
    return meta


class PaginatedFileOut(BaseModel):
    """Local pagination envelope (M8): legacy router must not depend on the
    canonical ``PaginatedResponse`` until it passes the reactivation
    checklist — the shape mirrors it (``items/total/page/page_size``)."""

    items: list[FileOut]
    total: int
    page: int
    page_size: int


@router.get("", response_model=PaginatedFileOut)
def list_files(entity_type: str | None = None, entity_id: int | None = None,
               page: int = Query(default=1, ge=1),
               page_size: int = Query(default=50, ge=1, le=100),
               db: Session = Depends(get_db),
               _u: CurrentUser = Depends(get_current_user)):
    # M8: фильтры применяются в SQL ДО limit/offset (раньше был
    # limit(200).all() + Python-фильтр — молча неверные выборки).
    q = db.query(FileMeta)
    if entity_type:
        q = q.filter(FileMeta.entity_type == entity_type)
    if entity_id is not None:
        q = q.filter(FileMeta.entity_id == entity_id)
    total = q.with_entities(func.count()).scalar() or 0
    rows = (
        q.order_by(FileMeta.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedFileOut(items=rows, total=total, page=page, page_size=page_size)
