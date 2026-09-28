"""Explicit offline adapters and canonical external snapshot operations.

Live LMS/Website contracts are not configured. A disabled adapter returns 503;
only EXTERNAL_ADAPTER_MODE=mock in non-production enables deterministic data.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import BusinessException, ConflictError
from app.core.exceptions import NotFound
from app.core.policies import apply_university_scope
from app.models.catalog import ITProgram, University
from app.models.external import ExternalApplication, ExternalSyncState
from app.models.interactions import UniversityProgram
from app.models.workflow_instances import WorkflowInstance
from app.models.workflow_templates import WorkflowTemplate
from app.modules.workflow_instances import service as workflow_service
from app.schemas.errors import ErrorCode


def require_adapter() -> None:
    if settings.external_adapter_mode != "mock" or settings.app_env.strip().lower() in {"prod", "production"}:
        raise BusinessException(ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE)


def mock_enabled() -> bool:
    return settings.external_adapter_mode == "mock" and settings.app_env.strip().lower() not in {"prod", "production"}


class MockWebsiteAdapter:
    """One stable external ID per university/program, no invented demand score."""

    def fetch(self, university_id: uuid.UUID, program_id: uuid.UUID) -> list[dict]:
        return [{
            "external_id": f"mock-website:{university_id}:{program_id}",
            "university_id": university_id,
            "program_id": program_id,
            "person_name": None,
            "status": "new",
            "flow_name": None,
            "external_created_at": datetime.now(timezone.utc),
        }]


def upsert_application(db: Session, payload: dict, *, ingest_channel: str, synced_at: datetime) -> ExternalApplication:
    """Shared exact-ID upsert for website API and file ingestion; no name matching."""
    external_id = str(payload["external_id"]).strip()
    if not external_id:
        raise ValueError("external_id is required")
    # Serialize first-ever inserts too; a row lock alone cannot protect a
    # missing row. PostgreSQL is the canonical integration database.
    db.execute(select(func.pg_advisory_xact_lock(func.hashtext("website:" + external_id))))
    row = db.scalar(select(ExternalApplication).where(
        ExternalApplication.source == "website", ExternalApplication.external_id == external_id,
    ).with_for_update())
    if row is None:
        row = ExternalApplication(source="website", external_id=external_id, ingest_channel=ingest_channel, synced_at=synced_at)
        db.add(row)
    university_id = payload.get("university_id")
    program_id = payload.get("program_id")
    if university_id and program_id and db.scalar(select(UniversityProgram.id).where(
        UniversityProgram.university_id == university_id, UniversityProgram.program_id == program_id,
    )):
        if row.university_id is not None and row.university_id != university_id:
            raise ConflictError(field="university_id")
        if row.workflow_instance_id is not None and row.program_id is not None and row.program_id != program_id:
            raise ConflictError(field="program_id")
        row.university_id = university_id
        row.program_id = program_id
    # Unresolved relations stay unresolved; never assign by person/program name.
    row.ingest_channel = ingest_channel
    for field in ("person_name", "status", "flow_name", "external_created_at"):
        if field in payload:
            setattr(row, field, payload[field])
    row.synced_at = synced_at
    db.flush()
    return row


def sync_mock(db: Session, university_id: uuid.UUID, source: str) -> dict:
    require_adapter()
    if db.get(University, university_id) is None:
        raise NotFound("University not found")
    program_id = db.scalar(select(UniversityProgram.program_id).where(
        UniversityProgram.university_id == university_id,
    ).order_by(UniversityProgram.program_id).limit(1))
    now = datetime.now(timezone.utc)
    if source == "lms":
        raise NotFound("LMS source removed")
    payloads = [] if program_id is None else MockWebsiteAdapter().fetch(university_id, program_id)
    unresolved = 0
    for payload in payloads:
        unresolved += upsert_application(db, payload, ingest_channel="mock", synced_at=now).program_id is None
    state = db.scalar(select(ExternalSyncState).where(
        ExternalSyncState.university_id == university_id, ExternalSyncState.source == source,
    ).with_for_update())
    if state is None:
        state = ExternalSyncState(university_id=university_id, source=source, synced_at=now)
        db.add(state)
    else:
        state.synced_at = now
    db.flush()
    if "audit_context" in db.info:
        from app.modules.audit.service import AuditService, context_for

        AuditService(db).log_event(
            context=context_for(db), action="IMPORT", entity_type="external_sync",
            entity_id=state.id, university_id=university_id,
            new_value={"audit_object_type": "external_sync",
                       "source": source, "processed": len(payloads), "unresolved": unresolved},
        )
    db.commit()
    return {"source": source, "mode": "mock", "synced_at": now, "processed": len(payloads), "unresolved": unresolved}


def university_data(db: Session, university_id: uuid.UUID, source: str) -> dict:
    if db.get(University, university_id) is None:
        raise NotFound("University not found")
    mock = mock_enabled()
    state = db.scalar(select(ExternalSyncState).where(
        ExternalSyncState.university_id == university_id, ExternalSyncState.source == source,
    ))
    if source == "lms":
        raise NotFound("LMS source removed")


def metrics(db: Session, user=None) -> dict:
    mock = mock_enabled()
    def scoped(statement, column):
        return apply_university_scope(statement, column, user) if user is not None else statement

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    website_query = select(func.count(ExternalApplication.id)).where(
        ExternalApplication.source == "website", ExternalApplication.external_created_at >= cutoff,
    )
    if not mock:
        website_query = website_query.where(ExternalApplication.ingest_channel == "file")
    website = db.scalar(scoped(website_query, ExternalApplication.university_id)) or 0
    website_sync = (db.scalar(scoped(select(func.max(ExternalSyncState.synced_at)).where(ExternalSyncState.source == "website"), ExternalSyncState.university_id))
                    if mock else db.scalar(scoped(select(func.max(ExternalApplication.synced_at)).where(ExternalApplication.ingest_channel == "file"), ExternalApplication.university_id)))
    return {"mode": "mock" if mock else "import", "website_applications_7d": website if website_sync else None,
            "website_synced_at": website_sync}


def create_workflow_from_application(db: Session, university_id: uuid.UUID, external_id: str,
                                     template_id: uuid.UUID | None, actor_sub: str) -> dict:
    statement = select(ExternalApplication).where(
        ExternalApplication.source == "website", ExternalApplication.external_id == external_id,
        ExternalApplication.university_id == university_id,
    )
    if not mock_enabled():
        statement = statement.where(ExternalApplication.ingest_channel == "file")
    application = db.scalar(statement.with_for_update())
    if application is None:
        raise NotFound("External application not found")
    if application.program_id is None:
        raise ConflictError(field="program_id")
    # Serialize requests across *different* applications for the same program.
    db.scalar(select(UniversityProgram.id).where(
        UniversityProgram.university_id == university_id,
        UniversityProgram.program_id == application.program_id,
    ).with_for_update())
    if application.workflow_instance_id is not None:
        instance = workflow_service.get_instance_detail(db, application.workflow_instance_id)
        return {"instance_id": instance.id, "university_id": university_id,
                "program_id": application.program_id, "external_id": external_id, "existing": True}
    existing = db.scalar(select(WorkflowInstance.id).where(
        WorkflowInstance.university_id == university_id, WorkflowInstance.program_id == application.program_id,
    ))
    if existing is not None:
        application.workflow_instance_id = existing
        db.commit()
        return {"instance_id": existing, "university_id": university_id,
                "program_id": application.program_id, "external_id": external_id, "existing": True}
    if template_id is None:
        templates = db.scalars(select(WorkflowTemplate.id).where(WorkflowTemplate.is_active.is_(True)).limit(2)).all()
        if len(templates) != 1:
            raise ConflictError(field="template_id")
        template_id = templates[0]
    instance = workflow_service.create_instance(db, university_id=university_id, template_id=template_id,
                                                program_id=application.program_id, actor_sub=actor_sub,
                                                external_application=application)
    return {"instance_id": instance.id, "university_id": university_id,
            "program_id": application.program_id, "external_id": external_id, "existing": False}
