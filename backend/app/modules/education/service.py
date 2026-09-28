"""Aggregate program indicators in one university scope; no learner PII."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFound
from app.core.policies import ensure_university_visible
from app.models.catalog import ITProgram, University
from app.models.education import ProgramEducationStats
from app.models.external import ExternalApplication
from app.models.interactions import UniversityProgram
from app.modules.education.schemas import ProgramEducationRead, UniversityEducationRead
from app.modules.integrations.service import mock_enabled


def university_education(db: Session, university_id: UUID, user) -> UniversityEducationRead:
    if db.get(University, university_id) is None:
        raise NotFound("University not found")
    ensure_university_visible(university_id, user)
    programs = db.execute(select(ITProgram.id, ITProgram.name).join(
        UniversityProgram, UniversityProgram.program_id == ITProgram.id,
    ).where(UniversityProgram.university_id == university_id).order_by(ITProgram.name)).all()
    stats = db.scalars(select(ProgramEducationStats).where(
        ProgramEducationStats.university_id == university_id,
    )).all()
    by_program: dict[UUID, dict[str, ProgramEducationStats]] = {}
    for row in stats:
        by_program.setdefault(row.program_id, {})[row.source] = row
    app_rows = db.execute(select(
        ExternalApplication.program_id, ExternalApplication.ingest_channel,
        func.count(ExternalApplication.id), func.max(ExternalApplication.synced_at),
    ).where(ExternalApplication.university_id == university_id,
            ExternalApplication.source == "website",
            ExternalApplication.program_id.is_not(None))
        .group_by(ExternalApplication.program_id, ExternalApplication.ingest_channel)).all()
    apps: dict[UUID, dict[str, tuple[int, object]]] = {}
    for program_id, channel, count, synced_at in app_rows:
        apps.setdefault(program_id, {})[channel] = (count, synced_at)
    result = []
    for program_id, name in programs:
        sources = by_program.get(program_id, {})
        selected = sources.get("lms") or sources.get("manual")
        if selected is None and mock_enabled():
            selected = sources.get("mock_lms")
        channels = apps.get(program_id, {})
        real = [value for channel, value in channels.items() if channel != "mock"]
        chosen = real or ([channels["mock"]] if mock_enabled() and "mock" in channels else [])
        result.append(ProgramEducationRead(
            program_id=program_id, program_name=name,
            learners_count=selected.learners_count if selected else 0,
            flows_count=selected.flows_count if selected else 0,
            applications_count=sum(count for count, _ in chosen),
            learner_source=selected.source if selected else None,
            learner_synced_at=selected.synced_at if selected else None,
            applications_synced_at=max((at for _, at in chosen), default=None),
        ))
    return UniversityEducationRead(
        university_id=university_id,
        learners_count=sum(item.learners_count for item in result),
        applications_count=sum(item.applications_count for item in result),
        flows_count=sum(item.flows_count for item in result),
        programs=result,
    )
