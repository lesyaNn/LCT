"""Explicit offline adapters and canonical external snapshot operations.

Live LMS/Website contracts are not configured. A disabled adapter returns 503;
only EXTERNAL_ADAPTER_MODE=mock in non-production enables deterministic data.
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import BusinessException, ConflictError
from app.core.exceptions import NotFound
from app.core.policies import apply_university_scope
from app.models.catalog import ITProgram, University
from app.models.external import ExternalApplication, ExternalSyncState
from app.models.interactions import Student, UniversityProgram
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

    def fetch(self, university_id: uuid.UUID, program_id: uuid.UUID, *, timeout_seconds: float = 10) -> list[dict]:
        return [{
            "external_id": f"mock-website:{university_id}:{program_id}",
            "university_id": university_id,
            "program_id": program_id,
            "person_name": None,
            "status": "new",
            "flow_name": None,
            "external_created_at": datetime.now(timezone.utc),
        }]


class MockLmsAdapter:
    """TEST/DEMO provider using the CRM-owned JSON learner contract."""

    def fetch(self, university_id: uuid.UUID, program_id: uuid.UUID, *, timeout_seconds: float = 10) -> list[dict]:
        return [{
            "external_id": f"mock-lms:{university_id}:{program_id}",
            "program_id": program_id,
            "full_name": "Тестовый обучающийся",
            "group_name": "Тестовый поток",
            "status": "active",
            "started_at": date(2026, 1, 1),
            "progress": 0,
        }]


class ExternalLmsAdapter(Protocol):
    """Provider boundary: fetch CRM learner DTOs with a bounded request timeout."""

    def fetch(self, university_id: uuid.UUID, program_id: uuid.UUID, *, timeout_seconds: float = 10) -> list[dict]: ...


class WebsiteAdapter(Protocol):
    """Provider boundary: fetch CRM application DTOs with a bounded request timeout."""

    def fetch(self, university_id: uuid.UUID, program_id: uuid.UUID, *, timeout_seconds: float = 10) -> list[dict]: ...


def fetch_from_provider(adapter: ExternalLmsAdapter | WebsiteAdapter,
                        university_id: uuid.UUID, program_id: uuid.UUID,
                        *, timeout_seconds: float = 10) -> list[dict]:
    """Bound provider fetch time and report failures through the typed API error."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(adapter.fetch, university_id, program_id,
                                 timeout_seconds=timeout_seconds)
        return future.result(timeout=timeout_seconds)
    except Exception as exc:
        raise BusinessException(ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE) from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


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


def upsert_lms_student(db: Session, university_id: uuid.UUID, payload: dict, *, synced_at: datetime,
                       source: str = "lms") -> Student | None:
    """Match only by stable external ID and an existing university/program link."""
    program_id = payload["program_id"]
    if db.scalar(select(UniversityProgram.id).where(
        UniversityProgram.university_id == university_id,
        UniversityProgram.program_id == program_id,
    )) is None:
        return None
    external_id = str(payload["external_id"]).strip()
    db.execute(select(func.pg_advisory_xact_lock(func.hashtext("lms:" + external_id))))
    row = db.scalar(select(Student).where(Student.external_id == external_id).with_for_update())
    if row is not None and (row.source != source or row.university_id != university_id or row.program_id != program_id):
        raise ConflictError(field="external_id")
    if row is None:
        row = Student(external_id=external_id, university_id=university_id,
                      program_id=program_id, full_name=payload["full_name"],
                      started_at=payload["started_at"])
        db.add(row)
    row.full_name = payload["full_name"]
    row.group_name = payload.get("group_name")
    row.status = getattr(payload["status"], "value", payload["status"])
    row.started_at = payload["started_at"]
    row.progress = payload.get("progress")
    row.source = source
    row.synced_at = synced_at
    db.flush()
    return row


def ingest_lms(db: Session, university_id: uuid.UUID, learners: list[dict]) -> dict:
    """Apply validated CRM JSON in one transaction; unresolved programs remain untouched."""
    if db.get(University, university_id) is None:
        raise NotFound("University not found")
    now = datetime.now(timezone.utc)
    unresolved = sum(upsert_lms_student(db, university_id, item, synced_at=now) is None
                     for item in learners)
    state = db.scalar(select(ExternalSyncState).where(
        ExternalSyncState.university_id == university_id,
        ExternalSyncState.source == "lms",
    ).with_for_update())
    if state is None:
        state = ExternalSyncState(university_id=university_id, source="lms", synced_at=now)
        db.add(state)
    else:
        state.synced_at = now
    db.flush()
    if "audit_context" in db.info:
        from app.modules.audit.service import AuditService, context_for
        AuditService(db).log_event(
            context=context_for(db), action="IMPORT", entity_type="external_sync",
            entity_id=state.id, university_id=university_id,
            new_value={"source": "lms", "processed": len(learners) - unresolved,
                       "unresolved": unresolved},
        )
    db.commit()
    return {"source": "lms", "mode": "ingest", "synced_at": now,
            "processed": len(learners) - unresolved, "unresolved": unresolved}


def ingest_website(db: Session, university_id: uuid.UUID, applications: list[dict]) -> dict:
    """Apply website JSON by exact external ID; unknown university programs stay unresolved."""
    if db.get(University, university_id) is None:
        raise NotFound("University not found")
    now = datetime.now(timezone.utc)
    unresolved = 0
    for item in applications:
        row = upsert_application(db, {**item, "university_id": university_id},
                                 ingest_channel="api", synced_at=now)
        unresolved += row.program_id is None
    state = db.scalar(select(ExternalSyncState).where(
        ExternalSyncState.university_id == university_id,
        ExternalSyncState.source == "website",
    ).with_for_update())
    if state is None:
        state = ExternalSyncState(university_id=university_id, source="website", synced_at=now)
        db.add(state)
    else:
        state.synced_at = now
    db.flush()
    if "audit_context" in db.info:
        from app.modules.audit.service import AuditService, context_for
        AuditService(db).log_event(
            context=context_for(db), action="IMPORT", entity_type="external_sync",
            entity_id=state.id, university_id=university_id,
            new_value={"source": "website", "processed": len(applications) - unresolved,
                       "unresolved": unresolved},
        )
    db.commit()
    return {"source": "website", "mode": "ingest", "synced_at": now,
            "processed": len(applications) - unresolved, "unresolved": unresolved}


def sync_mock(db: Session, university_id: uuid.UUID, source: str) -> dict:
    require_adapter()
    if db.get(University, university_id) is None:
        raise NotFound("University not found")
    program_id = db.scalar(select(UniversityProgram.program_id).where(
        UniversityProgram.university_id == university_id,
    ).order_by(UniversityProgram.program_id).limit(1))
    now = datetime.now(timezone.utc)
    lms_adapter: ExternalLmsAdapter = MockLmsAdapter()
    website_adapter: WebsiteAdapter = MockWebsiteAdapter()
    payloads = [] if program_id is None else (
        fetch_from_provider(lms_adapter, university_id, program_id) if source == "lms"
        else fetch_from_provider(website_adapter, university_id, program_id)
    )
    unresolved = 0
    for payload in payloads:
        if source == "lms":
            unresolved += upsert_lms_student(db, university_id, payload, synced_at=now,
                                             source="mock_lms") is None
        else:
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
        allowed_sources = ("lms", "mock_lms") if mock else ("lms",)
        students = db.scalars(select(Student).where(
            Student.university_id == university_id, Student.source.in_(allowed_sources),
        ).order_by(Student.id)).all()
        return {"university_id": university_id, "source": source,
                "mode": "mock" if mock else "import" if students else "unconfigured",
                "synced_at": state.synced_at if state else None,
                "students": [{"id": row.external_id, "name": row.full_name,
                              "program_id": row.program_id, "flow": row.group_name,
                              "progress": row.progress, "source": row.source, "synced_at": row.synced_at}
                             for row in students], "applications": []}
    statement = select(
        ExternalApplication.program_id, ITProgram.name, func.count(ExternalApplication.id),
        func.min(ExternalApplication.external_id), func.max(ExternalApplication.synced_at),
        func.min(cast(ExternalApplication.workflow_instance_id, String)),
    ).join(ITProgram, ITProgram.id == ExternalApplication.program_id).where(
        ExternalApplication.university_id == university_id,
        ExternalApplication.source == "website",
    )
    if not mock:
        statement = statement.where(ExternalApplication.ingest_channel != "mock")
    rows = db.execute(statement.group_by(
        ExternalApplication.program_id, ITProgram.name,
    ).order_by(ITProgram.name)).all()
    applications = [{"id": str(representative), "university_id": university_id,
                     "program_id": program_id, "program_name": name,
                     "applications_count": count, "demand_score": None,
                     "source": "website", "synced_at": latest,
                     "workflow_instance_id": workflow_id}
                    for program_id, name, count, representative, latest, workflow_id in rows]
    return {"university_id": university_id, "source": source,
            "mode": "mock" if mock else "import" if rows else "unconfigured",
            "synced_at": state.synced_at if mock and state else max((item[4] for item in rows), default=None),
            "students": [], "applications": applications}


def metrics(db: Session, user=None) -> dict:
    mock = mock_enabled()
    def scoped(statement, column):
        return apply_university_scope(statement, column, user) if user is not None else statement

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    website_query = select(func.count(ExternalApplication.id)).where(
        ExternalApplication.source == "website", ExternalApplication.external_created_at >= cutoff,
    )
    if not mock:
        website_query = website_query.where(ExternalApplication.ingest_channel != "mock")
    website = db.scalar(scoped(website_query, ExternalApplication.university_id)) or 0
    lms_sources = ("lms", "mock_lms") if mock else ("lms",)
    lms = db.scalar(scoped(select(func.count(Student.id)).where(Student.source.in_(lms_sources)), Student.university_id)) or 0
    website_sync = (db.scalar(scoped(select(func.max(ExternalSyncState.synced_at)).where(ExternalSyncState.source == "website"), ExternalSyncState.university_id))
                    if mock else db.scalar(scoped(select(func.max(ExternalApplication.synced_at)).where(ExternalApplication.ingest_channel != "mock"), ExternalApplication.university_id)))
    lms_sync = db.scalar(scoped(select(func.max(ExternalSyncState.synced_at)).where(ExternalSyncState.source == "lms"), ExternalSyncState.university_id))
    return {"mode": "mock" if mock else "import", "website_applications_7d": website if website_sync else None,
            "website_synced_at": website_sync, "lms_students": lms if lms_sync else None,
            "lms_synced_at": lms_sync}


def create_workflow_from_application(db: Session, university_id: uuid.UUID, external_id: str,
                                     template_id: uuid.UUID | None, actor_sub: str) -> dict:
    statement = select(ExternalApplication).where(
        ExternalApplication.source == "website", ExternalApplication.external_id == external_id,
        ExternalApplication.university_id == university_id,
    )
    if not mock_enabled():
        statement = statement.where(ExternalApplication.ingest_channel != "mock")
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
        from app.db.seed_workflow import TEMPLATE_NAME as SPEC_TEMPLATE_NAME
        template_id = db.scalar(select(WorkflowTemplate.id).where(
            WorkflowTemplate.name == SPEC_TEMPLATE_NAME, WorkflowTemplate.is_active.is_(True),
        ))
        if template_id is None:
            templates = db.scalars(select(WorkflowTemplate.id).where(
                WorkflowTemplate.is_active.is_(True)).limit(2)).all()
            if len(templates) != 1:
                raise ConflictError(field="template_id")
            template_id = templates[0]
    instance = workflow_service.create_instance(db, university_id=university_id, template_id=template_id,
                                                program_id=application.program_id, actor_sub=actor_sub,
                                                external_application=application)
    return {"instance_id": instance.id, "university_id": university_id,
            "program_id": application.program_id, "external_id": external_id, "existing": False}
