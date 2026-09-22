"""P2-11-03: Health Score edge cases, границы 0/100, детерминизм (PostgreSQL)."""

import os
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

import app.models  # noqa: F401 (register metadata)
from app.models.catalog import ITDirection, ITProgram, University
from app.models.interactions import Document, UniversityProgram
from app.models.teachers import Teacher, TeacherCertificate, TeacherProgram
from app.models.workflow_instances import (
    InstanceStage,
    WorkflowInstance,
    WorkflowTask,
)
from app.models.workflow_templates import WorkflowTemplate, WorkflowStage
from app.modules.health_score.aggregate import aggregate_scores
from app.modules.health_score.health_service import build_reasons, calculate_health_score
from app.modules.health_score.schemas import HealthScoreCounters
from app.modules.health_score.status import get_health_status

TODAY = date(2026, 9, 20)
NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")


@pytest.fixture()
def engine():
    """PostgreSQL integration DB (canonical SQL migrations; skips w/o PG)."""
    from tests.db_helpers import require_pg_engine

    eng = require_pg_engine(TEST_URL)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    with Session(engine) as session:
        yield session


def _uni(db: Session, name="Вуз Edge") -> University:
    uni = University(id=uuid4(), name=name)
    db.add(uni)
    db.flush()
    return uni


def _program(db: Session, uni_id, *, status="active", launch=None):
    direction = ITDirection(id=uuid4(), code=f"E-{uuid4().hex[:8]}", name="Направление")
    prog = ITProgram(id=uuid4(), direction_id=direction.id, name="Программа")
    db.add_all([direction, prog])
    db.flush()
    db.add(UniversityProgram(
        id=uuid4(), university_id=uni_id, program_id=prog.id,
        status=status, launch_date=launch))
    db.flush()
    return prog


def _workflow(db: Session, uni_id):
    template = WorkflowTemplate(id=uuid4(), name="Ш")
    db.add(template)
    db.flush()
    tpl_stage = WorkflowStage(
        id=uuid4(), template_id=template.id, name="Этап", order_index=1)
    db.add(tpl_stage)
    db.flush()
    instance = WorkflowInstance(
        id=uuid4(), template_id=template.id, university_id=uni_id,
        status="active")
    db.add(instance)
    db.flush()
    return instance, tpl_stage


# ------------------------------------------------------- границы 0/85/60/100

@pytest.mark.parametrize(
    ("parts", "expected", "status"),
    [
        ((100, 100, 100, 100, 100), 100, "green"),
        ((100, 100, 100, 100, 0), 85, "green"),   # boundary green
        ((100, 100, 100, 95, 0), 84, "yellow"),   # boundary yellow
        ((0, 100, 100, 100, 0), 60, "yellow"),    # boundary yellow/red
        ((0, 100, 100, 95, 0), 59, "red"),
        ((0, 0, 0, 0, 0), 0, "red"),
    ],
)
def test_score_boundaries(parts, expected, status):
    assert aggregate_scores(*parts) == expected
    assert get_health_status(expected).value == status


def test_single_component_100_weight():
    assert aggregate_scores(0, 100, 0, 0, 0) == 20
    assert aggregate_scores(0, 0, 0, 0, 100) == 15


# ------------------------------------------------------------- edge cases

def test_empty_university_all_neutral(db):
    uni = _uni(db)
    db.commit()
    resp = calculate_health_score(db, uni.id, TODAY, NOW)
    assert resp.score == 100
    assert resp.status == "green"
    assert resp.reasons == []


def test_all_critical_tasks_T_zero(db):
    uni = _uni(db)
    instance, _ = _workflow(db, uni.id)
    for _ in range(13):  # 13 * 8 = 104 → floor 0
        db.add(WorkflowTask(
            id=uuid4(), instance_id=instance.id, title="Задача",
            deadline=(NOW - timedelta(days=30)).date(), status="open",
            priority="normal"))
    db.commit()
    resp = calculate_health_score(db, uni.id, TODAY, NOW)
    assert resp.breakdown.tasks == 0
    assert resp.input_counters.overdue_critical_tasks == 13
    assert any(r.code == "OVERDUE_CRITICAL_TASKS" for r in resp.reasons)


def test_all_documents_expired_D_zero(db):
    uni = _uni(db)
    for doc_type in ("contract", "license"):
        db.add(Document(
            id=uuid4(), university_id=uni.id, document_type=doc_type,
            title="Док", file_path="/f", file_name="d.pdf",
            status_raw="signed", expires_at=TODAY - timedelta(days=1),
            uploaded_by_keycloak_sub="t"))
    db.commit()
    resp = calculate_health_score(db, uni.id, TODAY, NOW)
    assert resp.breakdown.documents == 0
    assert any(r.code == "INVALID_DOCUMENTS" for r in resp.reasons)


def test_all_stages_late_S_zero(db):
    uni = _uni(db)
    instance, tpl_stage = _workflow(db, uni.id)
    db.add(InstanceStage(
        id=uuid4(), instance_id=instance.id, template_stage_id=tpl_stage.id,
        order_index=1, name="Этап", status="completed",
        due_date=(NOW - timedelta(days=10)).date(),
        completed_at=NOW - timedelta(days=1)))
    db.commit()
    resp = calculate_health_score(db, uni.id, TODAY, NOW)
    assert resp.breakdown.stages == 0
    assert any(r.code == "OVERDUE_STAGES" for r in resp.reasons)


def test_all_teachers_expired_E_zero(db):
    uni = _uni(db)
    prog = _program(db, uni.id, status="active", launch=TODAY + timedelta(days=60))
    teacher = Teacher(id=uuid4(), university_id=uni.id, full_name="Учитель",
                      email=f"e-{uuid4()}@x.local")
    db.add(teacher)
    db.flush()
    db.add(TeacherProgram(id=uuid4(), teacher_id=teacher.id,
                          program_id=prog.id, assigned_at=TODAY))
    db.add(TeacherCertificate(
        id=uuid4(), teacher_id=teacher.id, certificate_name="Обязательный",
        issued_at=TODAY - timedelta(days=400),
        expires_at=TODAY - timedelta(days=1), is_mandatory=True))
    db.commit()
    resp = calculate_health_score(db, uni.id, TODAY, NOW)
    assert resp.breakdown.teachers == 0
    assert any(r.code == "EXPIRED_CERTIFICATES" for r in resp.reasons)


def test_all_programs_overdue_L_zero(db):
    uni = _uni(db)
    _program(db, uni.id, status="active", launch=TODAY - timedelta(days=1))
    db.commit()
    resp = calculate_health_score(db, uni.id, TODAY, NOW)
    assert resp.breakdown.launch == 0
    assert any(r.code == "LAUNCH_DELAYED" for r in resp.reasons)


# --------------------------------------------------------- детерминизм

def test_deterministic_50_runs(db):
    uni = _uni(db)
    db.add(Document(
        id=uuid4(), university_id=uni.id, document_type="act",
        title="Акт", file_path="/f", file_name="a.pdf",
        status_raw="signed", expires_at=None, uploaded_by_keycloak_sub="t"))
    db.commit()
    expected = calculate_health_score(db, uni.id, TODAY, NOW).model_dump(mode="json")
    for _ in range(50):
        assert calculate_health_score(db, uni.id, TODAY, NOW).model_dump(mode="json") == expected


def test_reasons_severity_and_counters_match_db(db):
    uni = _uni(db)
    db.commit()
    resp = calculate_health_score(db, uni.id, TODAY, NOW)
    assert resp.input_counters.active_programs == 0
    assert resp.input_counters.teachers_required == 0
    assert build_reasons(HealthScoreCounters()).__len__() == 0
