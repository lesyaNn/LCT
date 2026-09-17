from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import CurrentUser, get_current_user
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
        raise HTTPException(413, "File too large")
    if f.content_type and f.content_type not in ALLOWED:
        raise HTTPException(415, f"MIME not allowed: {f.content_type}")
    key = storage.save_file(f.filename or "file", content)
    meta = FileMeta(original_filename=f.filename or "file", storage_key=key,
                    content_type=f.content_type or "", size=len(content),
                    uploaded_by=user.id, entity_type=entity_type, entity_id=entity_id)
    db.add(meta)
    db.commit()
    db.refresh(meta)
    return meta


@router.get("", response_model=list[FileOut])
def list_files(entity_type: str | None = None, entity_id: int | None = None,
               db: Session = Depends(get_db),
               _u: CurrentUser = Depends(get_current_user)):
    q = db.query(FileMeta).order_by(FileMeta.id.desc()).limit(200)
    rows = q.all()
    if entity_type:
        rows = [r for r in rows if r.entity_type == entity_type]
    if entity_id:
        rows = [r for r in rows if r.entity_id == entity_id]
    return rows
