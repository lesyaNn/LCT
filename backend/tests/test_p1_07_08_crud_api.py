"""P1-07-01 / P1-08-01: HTTP CRUD for meetings and students.

Mounted routes (see ``app.modules.meetings.router`` /
``app.modules.students.router``):

* ``POST`` / ``GET`` ``/api/v1/universities/{id}/meetings|students``;
* ``GET`` / ``PATCH`` / ``DELETE`` ``/api/v1/meetings/{id}``,
  ``/api/v1/students/{id}``.

DB integration tests require PostgreSQL via ``TEST_DATABASE_URL`` (schema
from canonical SQL migrations, per-test reset). Pure-unit DTO validation
runs anywhere.
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.models  # noqa: F401 (register metadata on Base)
from app.models.catalog import ITDirection, ITProgram, University

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")


def _tag() -> str:
    return uuid.uuid4().hex[:8]


@pytest.fixture()
def engine():
    from tests.db_helpers import require_pg_engine

    eng = require_pg_engine(TEST_URL)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture()
def client(engine):
    """TestClient with get_db overridden to the PG test engine + dev bypass."""
    from app.config import settings
    from app.db.session import get_db
    from app.main import app

    def _override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _override
    old = settings.auth_dev_bypass
    settings.auth_dev_bypass = True
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        settings.auth_dev_bypass = old


def _make_university(db: Session) -> University:
    u = University(name=f"Uni-{_tag()}", city="Moscow")
    db.add(u)
    db.flush()
    return u


def _make_program(db: Session) -> ITProgram:
    d = ITDirection(code=f"D-{_tag()}", name=f"Dir {_tag()}")
    db.add(d)
    db.flush()
    p = ITProgram(direction_id=d.id, name=f"Prog-{_tag()}", description="")
    db.add(p)
    db.flush()
    return p


def _meeting_body(**over) -> dict:
    body = {
        "meeting_type": "online",
        "subject": "Sync",
        "participants": [{"name": "Rector"}],
        "meeting_at": datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc).isoformat(),
    }
    body.update(over)
    return body


def _student_body(program_id: uuid.UUID, **over) -> dict:
    body = {
        "external_id": f"EXT-{_tag()}",
        "program_id": str(program_id),
        "full_name": "Ivan Ivanov",
        "group_name": "G-1",
        "status": "active",
        "started_at": date(2026, 9, 1).isoformat(),
    }
    body.update(over)
    return body


# ================================================================ meetings ==


def test_meetings_crud_lifecycle(db: Session, client: TestClient):
    u = _make_university(db)
    db.commit()

    created = client.post(f"/api/v1/universities/{u.id}/meetings", json=_meeting_body())
    assert created.status_code == 201, created.text
    mid = created.json()["id"]
    assert created.json()["university_id"] == str(u.id)

    listed = client.get(f"/api/v1/universities/{u.id}/meetings")
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == mid

    got = client.get(f"/api/v1/meetings/{mid}")
    assert got.status_code == 200, got.text
    assert got.json()["subject"] == "Sync"

    patched = client.patch(f"/api/v1/meetings/{mid}", json={"subject": "Kickoff"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["subject"] == "Kickoff"

    deleted = client.delete(f"/api/v1/meetings/{mid}")
    assert deleted.status_code == 204, deleted.text
    assert client.get(f"/api/v1/meetings/{mid}").status_code == 404


def test_meetings_pagination_and_404(db: Session, client: TestClient):
    u = _make_university(db)
    db.commit()
    for i in range(3):
        r = client.post(
            f"/api/v1/universities/{u.id}/meetings",
            json=_meeting_body(subject=f"M-{i}"),
        )
        assert r.status_code == 201, r.text
    p1 = client.get(f"/api/v1/universities/{u.id}/meetings", params={"page_size": 2})
    assert p1.json()["total"] == 3 and len(p1.json()["items"]) == 2
    p2 = client.get(
        f"/api/v1/universities/{u.id}/meetings", params={"page_size": 2, "page": 2}
    )
    assert len(p2.json()["items"]) == 1

    assert client.get(f"/api/v1/meetings/{uuid.uuid4()}").status_code == 404
    assert (
        client.post(
            f"/api/v1/universities/{uuid.uuid4()}/meetings", json=_meeting_body()
        ).status_code
        == 404
    )


def test_meetings_validation(db: Session, client: TestClient):
    u = _make_university(db)
    db.commit()
    # naive datetime -> 422 (tz-aware required)
    bad = client.post(
        f"/api/v1/universities/{u.id}/meetings",
        json=_meeting_body(meeting_at="2026-09-20T10:00:00"),
    )
    assert bad.status_code == 422, bad.text
    # bad enum -> 422
    bad_enum = client.post(
        f"/api/v1/universities/{u.id}/meetings",
        json=_meeting_body(meeting_type="telepathy"),
    )
    assert bad_enum.status_code == 422, bad_enum.text
    # invalid UUID in path -> 422
    assert client.get("/api/v1/meetings/not-a-uuid").status_code == 422


# ================================================================ students ==


def test_students_crud_lifecycle(db: Session, client: TestClient):
    u = _make_university(db)
    p = _make_program(db)
    db.commit()

    created = client.post(
        f"/api/v1/universities/{u.id}/students", json=_student_body(p.id)
    )
    assert created.status_code == 201, created.text
    sid = created.json()["id"]
    assert created.json()["university_id"] == str(u.id)

    listed = client.get(f"/api/v1/universities/{u.id}/students")
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1

    got = client.get(f"/api/v1/students/{sid}")
    assert got.status_code == 200 and got.json()["full_name"] == "Ivan Ivanov"

    patched = client.patch(
        f"/api/v1/students/{sid}", json={"status": "graduated", "group_name": "G-2"}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["status"] == "graduated"

    assert client.delete(f"/api/v1/students/{sid}").status_code == 204
    assert client.get(f"/api/v1/students/{sid}").status_code == 404


def test_students_unique_and_fk(db: Session, client: TestClient):
    u = _make_university(db)
    p = _make_program(db)
    db.commit()
    body = _student_body(p.id, external_id="DUP-1")
    assert client.post(f"/api/v1/universities/{u.id}/students", json=body).status_code == 201
    # duplicate external_id -> 409 via central IntegrityError mapping
    dup = client.post(f"/api/v1/universities/{u.id}/students", json=body)
    assert dup.status_code == 409, dup.text
    # unknown program -> 404
    bad_prog = client.post(
        f"/api/v1/universities/{u.id}/students",
        json=_student_body(uuid.uuid4()),
    )
    assert bad_prog.status_code == 404, bad_prog.text
    # unknown university -> 404
    assert (
        client.post(
            f"/api/v1/universities/{uuid.uuid4()}/students", json=_student_body(p.id)
        ).status_code
        == 404
    )


def test_students_rbac_and_validation(db: Session, client: TestClient):
    u = _make_university(db)
    p = _make_program(db)
    db.commit()
    # unauthenticated (bypass off for one call) -> 401
    from app.config import settings

    settings.auth_dev_bypass = False
    try:
        assert (
            client.get(f"/api/v1/universities/{u.id}/students").status_code == 401
        )
    finally:
        settings.auth_dev_bypass = True
    # bad status enum -> 422
    bad = client.post(
        f"/api/v1/universities/{u.id}/students",
        json=_student_body(p.id, status="flying"),
    )
    assert bad.status_code == 422, bad.text


# ============================================================ pure-unit ==


def test_meeting_dto_tz_validation():
    from app.modules.meetings.schemas import MeetingCreate

    with pytest.raises(Exception):
        MeetingCreate(subject="x", meeting_at=datetime(2026, 9, 20, 10, 0))
    ok = MeetingCreate(
        subject="x", meeting_at=datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc)
    )
    assert ok.meeting_type.value == "online" and ok.participants == []


def test_student_dto_validation():
    from app.modules.students.schemas import StudentCreate

    with pytest.raises(Exception):
        StudentCreate(
            external_id="E",
            program_id=uuid.uuid4(),
            full_name="",
            started_at=date(2026, 9, 1),
        )
    ok = StudentCreate(
        external_id="E",
        program_id=uuid.uuid4(),
        full_name="Name",
        started_at=date(2026, 9, 1),
    )
    assert ok.status.value == "active"
