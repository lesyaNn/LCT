"""Private notes API. Every query is constrained to the Keycloak subject."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import BusinessException, ConflictError
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.personal_note import NoteFolder, PersonalNote
from app.modules.personal_notes import service
from app.modules.personal_notes.schemas import (
    NoteCreate, NoteFolderRead, NoteFolderWrite, NoteLinkOption, NoteList,
    NoteRead, NoteUpdate, ResolveLinksRequest, ResolvedLink,
)
from app.schemas.errors import ErrorCode

router = APIRouter(prefix="/notes", tags=["Notes"])


@router.get("/folders", response_model=list[NoteFolderRead], summary="Личные папки заметок")
def list_folders(response: Response, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    return list(db.scalars(select(NoteFolder).where(NoteFolder.owner_sub == service.owner(user)).order_by(NoteFolder.name)))


@router.post("/folders", response_model=NoteFolderRead, status_code=201, summary="Создать папку заметок")
def create_folder(body: NoteFolderWrite, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    folder = NoteFolder(owner_sub=service.owner(user), name=body.name)
    db.add(folder)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(field="name") from exc
    db.refresh(folder)
    return folder


@router.patch("/folders/{folder_id}", response_model=NoteFolderRead, summary="Переименовать личную папку")
def rename_folder(folder_id: UUID, body: NoteFolderWrite, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    folder = service.own_folder(db, folder_id, user)
    folder.name = body.name
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(field="name") from exc
    db.refresh(folder)
    return folder


@router.delete("/folders/{folder_id}", status_code=204, summary="Удалить папку, сохранив заметки")
def delete_folder(folder_id: UUID, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    folder = service.own_folder(db, folder_id, user)
    db.execute(update(PersonalNote).where(PersonalNote.owner_sub == service.owner(user), PersonalNote.folder_id == folder_id)
               .values(folder_id=None, revision=PersonalNote.revision + 1,
                       updated_at=datetime.now(timezone.utc)))
    db.delete(folder)
    db.commit()


@router.get("/link-options", response_model=list[NoteLinkOption], summary="Доступные объекты CRM для ссылки")
def link_options(response: Response, q: str = Query(min_length=2, max_length=100), db: Session = Depends(get_db),
                 user: CurrentUser = Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    return service.link_options(db, user, q)


@router.post("/resolve-links", response_model=list[ResolvedLink], summary="Проверить доступность ссылок заметки")
def resolve_links(body: ResolveLinksRequest, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    service.owner(user)
    return [service.resolve_link(db, user, href) for href in dict.fromkeys(body.hrefs)]


@router.get("", response_model=NoteList, summary="Найти личные заметки")
def list_notes(response: Response, view: str = Query(default="all", pattern="^(all|pinned|recent|trash)$"),
               q: str = Query(default="", max_length=200), folder_id: UUID | None = None,
               sort: str = Query(default="updated", pattern="^(updated|title)$"),
               page: int = Query(default=1, ge=1), page_size: int = Query(default=30, ge=1, le=100),
               db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    rows, total = service.list_notes(db, user, view=view, q=q, folder_id=folder_id,
                                     sort=sort, page=page, page_size=page_size)
    return NoteList(items=[service.summary(note, q=q) for note in rows], total=total, page=page, page_size=page_size)


@router.post("", response_model=NoteRead, status_code=201, summary="Создать личную заметку")
def create_note(body: NoteCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    if body.folder_id is not None:
        service.own_folder(db, body.folder_id, user)
    note = PersonalNote(owner_sub=service.owner(user), title=body.title.strip() or "Без названия",
                        content=body.content, folder_id=body.folder_id,
                        search_text=f"{body.title.strip() or 'Без названия'}\n{body.content}".casefold())
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@router.get("/{note_id}", response_model=NoteRead, summary="Открыть личную заметку")
def get_note(note_id: UUID, response: Response, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    return service.own_note(db, note_id, user)


@router.patch("/{note_id}", response_model=NoteRead, summary="Сохранить заметку с проверкой версии")
def update_note(note_id: UUID, body: NoteUpdate, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    note = service.own_note(db, note_id, user)
    changes = body.model_dump(exclude_unset=True, exclude={"revision"})
    if not changes:
        return note
    return service.save_note(db, note, user, revision=body.revision, changes=changes)


@router.delete("/{note_id}", status_code=204, summary="Переместить заметку в корзину")
def delete_note(note_id: UUID, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    note = service.own_note(db, note_id, user)
    note.deleted_at = datetime.now(timezone.utc)
    note.revision += 1
    db.commit()


@router.post("/{note_id}/restore", response_model=NoteRead, summary="Восстановить заметку из корзины")
def restore_note(note_id: UUID, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    note = service.own_note(db, note_id, user, include_deleted=True)
    if note.deleted_at is None:
        raise BusinessException(ErrorCode.CONFLICT)
    note.deleted_at = None
    note.revision += 1
    db.commit()
    db.refresh(note)
    return note


@router.delete("/{note_id}/permanent", status_code=204, summary="Удалить личную заметку окончательно")
def purge_note(note_id: UUID, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    note = service.own_note(db, note_id, user, include_deleted=True)
    if note.deleted_at is None:
        raise BusinessException(ErrorCode.CONFLICT)
    db.delete(note)
    db.commit()
