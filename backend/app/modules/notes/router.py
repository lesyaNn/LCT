import logging
from functools import lru_cache
from typing import Literal
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import BusinessException
from app.core.openapi import file_response
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.modules.notes import service
from app.modules.notes.mentions import entity_mentions
from app.modules.notes.pdf import generate_note_pdf
from app.modules.notes.schemas import Mention, NoteCreate, NoteOut, NotePage, NotePdfExport, NoteUpdate
from app.schemas.errors import ErrorCode

router = APIRouter(prefix="/notes", tags=["Notes"])
logger = logging.getLogger(__name__)


@router.post("/export/pdf", response_class=Response,
             responses={200: file_response("Текущая заметка в PDF", "application/pdf")},
             summary="Экспортировать текущий текст заметки в PDF")
def export_pdf(data: NotePdfExport, db: Session = Depends(get_db),
               user: CurrentUser = Depends(get_current_user)):
    references_resolved = 0

    @lru_cache(maxsize=256)
    def resolve_link(href: str) -> str | None:
        nonlocal references_resolved
        parsed = urlsplit(href)
        if parsed.path != "/notes/reference" or parsed.netloc:
            return href
        if references_resolved >= 100:
            return None
        references_resolved += 1
        params = parse_qs(parsed.query)
        try:
            target_id = str(UUID(params["target_id"][0]))
            kind = params["kind"][0]
            university_id = UUID(params["university_id"][0]) if params.get("university_id") else None
            if kind not in Mention.model_fields["kind"].annotation.__args__:
                return None
            rows = entity_mentions(db, user, kind, "", target_id, university_id)
            return rows[0].href if rows else None
        except Exception:
            # Unavailable references remain readable text in the export.
            return None

    try:
        content = generate_note_pdf(data.title, data.document, settings.frontend_origin, resolve_link)
    except Exception as exc:
        logger.error("note_pdf_failed error_type=%s", type(exc).__name__)
        raise BusinessException(ErrorCode.REPORT_FAILED) from exc
    return Response(content, media_type="application/pdf", headers={
        "Content-Disposition": 'attachment; filename="note.pdf"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })


@router.post("/initialize", status_code=204, summary="Создать личную заметку с мини-гайдом один раз")
def initialize(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    service.initialize(db, user.id)
    return Response(status_code=204)


@router.get("", response_model=NotePage, summary="Личные заметки")
def list_notes(q: str = Query(default="", max_length=100),
               sort_by: Literal["created_at", "updated_at"] = "updated_at",
               sort_order: Literal["asc", "desc"] = "desc",
               offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100),
               db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    return service.list_notes(db, user.id, q, sort_by, sort_order, offset, limit)


@router.get("/mentions", response_model=list[Mention], summary="Доступные сущности для упоминания")
def mentions(kind: Literal["user", "university", "direction", "program", "vendor", "agreements", "entity", "workflow", "document", "contract", "license", "product", "responsible"],
             q: str = Query(default="", max_length=100), target_id: UUID | None = None,
             university_id: UUID | None = None,
             db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    return entity_mentions(db, user, kind, q.strip(), str(target_id) if target_id else None, university_id)


@router.post("", response_model=NoteOut, status_code=201, summary="Создать личную заметку")
def create(data: NoteCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    return service.create(db, user.id, data)


@router.get("/{note_id}", response_model=NoteOut, summary="Открыть личную заметку")
def get(note_id: UUID, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    return service.owned(db, user.id, note_id)


@router.patch("/{note_id}", response_model=NoteOut, summary="Сохранить личную заметку")
def save(note_id: UUID, data: NoteUpdate, db: Session = Depends(get_db),
         user: CurrentUser = Depends(get_current_user)):
    return service.save(db, user.id, note_id, data)


@router.delete("/{note_id}", status_code=204, summary="Удалить личную заметку")
def remove(note_id: UUID, revision: int = Query(ge=0), db: Session = Depends(get_db),
           user: CurrentUser = Depends(get_current_user)):
    service.remove(db, user.id, note_id, revision)
    return Response(status_code=204)
