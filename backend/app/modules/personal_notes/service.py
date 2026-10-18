"""Owner-scoped notes, search and safe CRM link discovery."""

from datetime import datetime, timedelta, timezone
from uuid import UUID
from urllib.parse import parse_qs, urlsplit
import re

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import BusinessException, ConflictError, SecurityError
from app.core.permissions import user_permissions
from app.core.policies import apply_university_scope, get_data_scope
from app.core.security import CurrentUser
from app.models.catalog import University
from app.models.interactions import Document, Meeting
from app.models.personal_note import NoteFolder, PersonalNote
from app.models.workflow_instances import InstanceStage, WorkflowInstance
from app.modules.catalog.repository import like_pattern
from app.modules.search import search as crm_search
from app.modules.personal_notes.schemas import NoteLinkOption, NoteSummary, ResolvedLink
from app.schemas.errors import ErrorCode


def owner(user: CurrentUser) -> str:
    if not user.id or not user.roles.intersection({"admin", "manager", "user"}):
        raise SecurityError(ErrorCode.FORBIDDEN)
    return user.id


def own_note(db: Session, note_id: UUID, user: CurrentUser, *, include_deleted: bool = False) -> PersonalNote:
    note = db.get(PersonalNote, note_id)
    if note is None or note.owner_sub != owner(user) or (note.deleted_at and not include_deleted):
        raise BusinessException(ErrorCode.NOT_FOUND)
    return note


def own_folder(db: Session, folder_id: UUID, user: CurrentUser) -> NoteFolder:
    folder = db.get(NoteFolder, folder_id)
    if folder is None or folder.owner_sub != owner(user):
        raise BusinessException(ErrorCode.NOT_FOUND)
    return folder


def summary(note: PersonalNote, *, q: str = "") -> NoteSummary:
    plain = re.sub(r"[\n\r\t*#>`_\[\]()!-]+", " ", note.content)
    plain = " ".join(plain.split())
    match_at = plain.casefold().find(q.strip().casefold()) if q.strip() else -1
    start = max(0, match_at - 50) if match_at >= 0 else 0
    excerpt = ("…" if start else "") + plain[start:start + 180]
    if start + 180 < len(plain):
        excerpt += "…"
    return NoteSummary(id=note.id, title=note.title, excerpt=excerpt, folder_id=note.folder_id,
                       pinned=note.pinned, revision=note.revision, updated_at=note.updated_at,
                       deleted_at=note.deleted_at)


def list_notes(db: Session, user: CurrentUser, *, view: str, q: str, folder_id: UUID | None,
               sort: str, page: int, page_size: int) -> tuple[list[PersonalNote], int]:
    stmt = select(PersonalNote).where(PersonalNote.owner_sub == owner(user))
    if view == "trash":
        stmt = stmt.where(PersonalNote.deleted_at.is_not(None))
    else:
        stmt = stmt.where(PersonalNote.deleted_at.is_(None))
    if view == "pinned":
        stmt = stmt.where(PersonalNote.pinned.is_(True))
    elif view == "recent":
        stmt = stmt.where(PersonalNote.updated_at >= datetime.now(timezone.utc) - timedelta(days=14))
    if folder_id is not None:
        own_folder(db, folder_id, user)
        stmt = stmt.where(PersonalNote.folder_id == folder_id)
    if q.strip():
        pattern = like_pattern(q.strip().casefold())
        stmt = stmt.where(PersonalNote.search_text.like(pattern, escape="\\"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    if sort == "title":
        stmt = stmt.order_by(PersonalNote.title.asc(), PersonalNote.id.asc())
    elif view == "trash":
        stmt = stmt.order_by(PersonalNote.deleted_at.desc(), PersonalNote.id.desc())
    else:
        stmt = stmt.order_by(PersonalNote.pinned.desc(), PersonalNote.updated_at.desc(), PersonalNote.id.desc())
    return list(db.scalars(stmt.offset((page - 1) * page_size).limit(page_size))), total


def save_note(db: Session, note: PersonalNote, user: CurrentUser, *, revision: int,
              changes: dict) -> PersonalNote:
    if "folder_id" in changes and changes["folder_id"] is not None:
        own_folder(db, changes["folder_id"], user)
    if "title" in changes:
        if changes["title"] is None:
            raise BusinessException(ErrorCode.VALIDATION_ERROR)
        changes["title"] = changes["title"].strip() or "Без названия"
    if "content" in changes and changes["content"] is None:
        raise BusinessException(ErrorCode.VALIDATION_ERROR)
    if "pinned" in changes and changes["pinned"] is None:
        raise BusinessException(ErrorCode.VALIDATION_ERROR)
    if "title" in changes or "content" in changes:
        changes["search_text"] = f"{changes.get('title', note.title)}\n{changes.get('content', note.content)}".casefold()
    result = db.execute(
        update(PersonalNote)
        .where(PersonalNote.id == note.id, PersonalNote.owner_sub == owner(user),
               PersonalNote.revision == revision, PersonalNote.deleted_at.is_(None))
        .values(**changes, revision=revision + 1, updated_at=datetime.now(timezone.utc))
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise ConflictError(field="revision")
    db.commit()
    db.expire_all()
    return db.get(PersonalNote, note.id)


def link_options(db: Session, user: CurrentUser, query: str) -> list[NoteLinkOption]:
    owner(user)
    term = query.strip()
    if len(term) < 2:
        return []
    hits = crm_search(db, user, term)
    options: list[NoteLinkOption] = []
    options.extend(NoteLinkOption(kind="university", title=hit.title, subtitle=hit.subtitle,
                                  href=f"/universities/{hit.id}") for hit in hits.universities)
    options.extend(NoteLinkOption(kind="workflow", title=hit.title, subtitle=hit.subtitle,
                                  href=f"/workflows/{hit.id}") for hit in hits.workflows)
    document_ids = [hit.id for hit in hits.documents]
    standalone_ids = set(db.scalars(select(Document.id).where(Document.id.in_(document_ids),
                        Document.contract_id.is_(None), Document.license_id.is_(None)))) if document_ids else set()
    options.extend(NoteLinkOption(kind="document", title=hit.title, subtitle=hit.subtitle,
                                  href=f"/universities/{hit.university_id}?tab=documents&document={hit.id}")
                   for hit in hits.documents if hit.university_id and hit.id in standalone_ids)
    permissions = user_permissions(user)
    sections = (
        ("Обзор", "/dashboard", "analytics.read"),
        ("Вузы", "/universities", "university.read"),
        ("Workflow", "/workflows", "workflow.read"),
        ("Отчёты", "/reports", "reports.read"),
        ("Заметки", "/notes", None),
    )
    options.extend(NoteLinkOption(kind="section", title=title, href=href)
                   for title, href, permission in sections
                   if term.casefold() in title.casefold() and (permission is None or permission in permissions))
    if "workflow.read" in user_permissions(user):
        pattern = like_pattern(term)
        stmt = apply_university_scope(
            select(InstanceStage.id, InstanceStage.name, WorkflowInstance.id, University.name)
            .join(WorkflowInstance, WorkflowInstance.id == InstanceStage.instance_id)
            .join(University, University.id == WorkflowInstance.university_id)
            .where(InstanceStage.name.ilike(pattern, escape="\\")), WorkflowInstance.university_id, user)
        for stage_id, stage_name, instance_id, university_name in db.execute(stmt.limit(5)):
            options.append(NoteLinkOption(kind="stage", title=stage_name, subtitle=university_name,
                                          href=f"/workflows/{instance_id}?stage={stage_id}"))
    if "university.read" in user_permissions(user):
        pattern = like_pattern(term)
        stmt = apply_university_scope(
            select(Meeting.id, Meeting.subject, Meeting.university_id, University.name)
            .join(University, University.id == Meeting.university_id)
            .where(Meeting.subject.ilike(pattern, escape="\\")), Meeting.university_id, user)
        for meeting_id, subject, university_id, university_name in db.execute(stmt.limit(5)):
            options.append(NoteLinkOption(kind="meeting", title=subject, subtitle=university_name,
                                          href=f"/universities/{university_id}?tab=meetings&meeting={meeting_id}"))
    options.extend(NoteLinkOption(kind="note", title=hit.title, href=f"/notes?note={hit.id}")
                   for hit in hits.notes)
    return options


def resolve_link(db: Session, user: CurrentUser, href: str) -> ResolvedLink:
    unavailable = ResolvedLink(href=href, available=False)
    if not href.startswith("/") or href.startswith("//") or len(href) > 512:
        return unavailable
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        return unavailable
    section_permissions = {
        "/dashboard": "analytics.read", "/universities": "university.read",
        "/workflows": "workflow.read", "/reports": "reports.read", "/notes": None,
    }
    if parsed.path in section_permissions and not parsed.query:
        required = section_permissions[parsed.path]
        if required is None or required in user_permissions(user):
            return ResolvedLink(href=href, title={"/dashboard": "Обзор", "/universities": "Вузы",
                                                   "/workflows": "Workflow", "/reports": "Отчёты",
                                                   "/notes": "Заметки"}[parsed.path], available=True)
    parts = parsed.path.strip("/").split("/")
    if parsed.path == "/notes":
        try:
            note_id = UUID(parse_qs(parsed.query).get("note", [""])[0])
        except ValueError:
            return unavailable
        note = db.get(PersonalNote, note_id)
        if note and note.owner_sub == owner(user) and note.deleted_at is None:
            return ResolvedLink(href=href, title=note.title, available=True)
        return unavailable
    if len(parts) != 2:
        return unavailable
    kind, raw_id = parts
    try:
        key = UUID(raw_id)
    except ValueError:
        return unavailable
    if kind == "universities" and "university.read" in user_permissions(user):
        if not get_data_scope(user).allows(key):
            return unavailable
        university = db.get(University, key)
        if university:
            qs = parse_qs(parsed.query)
            document = qs.get("document", [None])[0]
            meeting = qs.get("meeting", [None])[0]
            if document or meeting:
                try:
                    object_id = UUID(document or meeting)
                except ValueError:
                    return unavailable
                model = Document if document else Meeting
                item = db.get(model, object_id)
                if item is None or item.university_id != key:
                    return unavailable
                if document and (item.contract_id is not None or item.license_id is not None):
                    return unavailable
                return ResolvedLink(href=href, title=item.title if document else item.subject, available=True)
            return ResolvedLink(href=href, title=university.name, available=True)
    elif kind == "workflows" and "workflow.read" in user_permissions(user):
        workflow = db.get(WorkflowInstance, key)
        if workflow is None or not get_data_scope(user).allows(workflow.university_id):
            return unavailable
        stage = parse_qs(parsed.query).get("stage", [None])[0]
        if stage:
            try:
                stage_id = UUID(stage)
            except ValueError:
                return unavailable
            stage_row = db.get(InstanceStage, stage_id)
            if stage_row is None or stage_row.instance_id != key:
                return unavailable
            return ResolvedLink(href=href, title=stage_row.name, available=True)
        university = db.get(University, workflow.university_id)
        return ResolvedLink(href=href, title=university.name if university else "Workflow", available=True)
    return unavailable
