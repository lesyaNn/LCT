"""M4: unified university delete policy (pure-unit, sqlite).

Pins that a university hard-delete is refused while ANY business data
references it — including relations the DB would CASCADE away silently
(workflow instances, meetings), not just the RESTRICT ones (licenses).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import pytest

import app.models  # noqa: F401  (register canon metadata)
from app.core.exceptions import Conflict, NotFound
from app.db.base import Base
from app.models.catalog import Contract, License, University, UniversityResponsible
from app.models.interactions import (
    Document,
    InteractionNote,
    Meeting,
    UniversityProduct,
    UniversityProgram,
)
from app.models.workflow_instances import WorkflowInstance
from app.modules.catalog import service as catalog_service


@pytest.fixture()
def db():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(
        eng,
        tables=[
            University.__table__,
            License.__table__,
            Contract.__table__,
            WorkflowInstance.__table__,
            Meeting.__table__,
            Document.__table__,
            InteractionNote.__table__,
            UniversityProgram.__table__,
            UniversityProduct.__table__,
            UniversityResponsible.__table__,
        ],
    )
    with Session(eng) as session:
        yield session
    eng.dispose()


def _university(db: Session) -> University:
    uni = University(name="У-1", city="Казань")
    db.add(uni)
    db.commit()
    return uni


def test_delete_clean_university(db):
    uni = _university(db)
    catalog_service.delete_university(db, uni.id)
    assert db.get(University, uni.id) is None


def test_delete_missing_university_404(db):
    with pytest.raises(NotFound):
        catalog_service.delete_university(db, uuid.uuid4())


def test_delete_blocked_by_workflow_instance(db):
    uni = _university(db)
    db.add(WorkflowInstance(
        university_id=uni.id, template_id=uuid.uuid4(), status="active",
    ))
    db.commit()
    with pytest.raises(Conflict, match="workflow instances"):
        catalog_service.delete_university(db, uni.id)
    assert db.get(University, uni.id) is not None


def test_delete_blocked_by_meeting(db):
    uni = _university(db)
    db.add(Meeting(
        university_id=uni.id,
        subject="Созвон",
        meeting_at=datetime.now(timezone.utc),
        created_by_keycloak_sub="sub",
    ))
    db.commit()
    with pytest.raises(Conflict, match="meetings"):
        catalog_service.delete_university(db, uni.id)
    assert db.get(University, uni.id) is not None
