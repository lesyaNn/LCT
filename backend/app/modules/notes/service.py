"""Owner-scoped persistence with atomic compare-and-swap updates/deletes."""

import re
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import BusinessException, ConflictError
from app.models.note import Note, NoteOnboarding
from app.modules.catalog.repository import like_pattern
from app.modules.notes.schemas import NoteCreate, NoteOut, NotePage, NoteSummary, NoteUpdate
from app.modules.notes.welcome import WELCOME_TITLE, welcome_content
from app.schemas.errors import ErrorCode


def initialize(db: Session, subject: str) -> None:
    # The marker and note commit together. Parallel tabs can only create one
    # welcome note; deleting or editing it never causes it to be reseeded.
    first_visit = db.scalar(insert(NoteOnboarding).values(owner_sub=subject)
                            .on_conflict_do_nothing(index_elements=[NoteOnboarding.owner_sub])
                            .returning(NoteOnboarding.owner_sub))
    if first_visit is not None:
        db.add(Note(owner_sub=subject, title=WELCOME_TITLE, content=welcome_content(subject)))
    db.commit()


def snippet(content: str, query: str = "") -> str:
    text = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", content)
    text = " ".join(re.sub(r"[#*`~>\[\]]", "", text).split())
    position = text.casefold().find(query.casefold()) if query else 0
    start = max(0, position - 45)
    return ("…" if start else "") + text[start:start + 160]


def owned(db: Session, subject: str, note_id: UUID) -> Note:
    row = db.scalar(select(Note).where(Note.id == note_id, Note.owner_sub == subject))
    if row is None:
        raise BusinessException(ErrorCode.NOT_FOUND)
    return row


def list_notes(db: Session, subject: str, q: str, sort_by: Literal["created_at", "updated_at"],
               sort_order: Literal["asc", "desc"], offset: int, limit: int) -> NotePage:
    stmt = select(Note).where(Note.owner_sub == subject)
    if q.strip():
        pattern = like_pattern(q.strip())
        stmt = stmt.where(or_(Note.title.ilike(pattern, escape="\\"),
                              Note.content.ilike(pattern, escape="\\")))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    column = getattr(Note, sort_by)
    rows = db.scalars(stmt.order_by(column.asc() if sort_order == "asc" else column.desc(),
                                    Note.id).offset(offset).limit(limit))
    return NotePage(total=total, items=[NoteSummary(
        **NoteOut.model_validate(row).model_dump(exclude={"content"}),
        snippet=snippet(row.content, q.strip()),
    ) for row in rows])


def create(db: Session, subject: str, data: NoteCreate) -> Note:
    existing = db.get(Note, data.id)
    if existing is not None:
        return owned(db, subject, data.id)
    row = Note(**data.model_dump(), owner_sub=subject)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Another retry may have inserted the same ID concurrently.
        return owned(db, subject, data.id)
    db.refresh(row)
    return row


def save(db: Session, subject: str, note_id: UUID, data: NoteUpdate) -> Note:
    owned(db, subject, note_id)
    changed = db.execute(update(Note).where(
        Note.id == note_id, Note.owner_sub == subject, Note.revision == data.revision,
    ).values(title=data.title, content=data.content, revision=Note.revision + 1,
             updated_at=datetime.now(UTC)).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        db.rollback()
        raise ConflictError(field="revision")
    db.commit()
    db.expire_all()
    return owned(db, subject, note_id)


def remove(db: Session, subject: str, note_id: UUID, revision: int) -> None:
    owned(db, subject, note_id)
    changed = db.execute(delete(Note).where(
        Note.id == note_id, Note.owner_sub == subject, Note.revision == revision,
    ))
    if changed.rowcount != 1:
        db.rollback()
        raise ConflictError(field="revision")
    db.commit()
