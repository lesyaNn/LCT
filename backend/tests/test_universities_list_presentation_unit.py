"""Universities list presentation (pure-unit, sqlite).

Regression: GET /api/v1/universities must return related presentation data
(responsible / programs / current stage / last interaction / attention) in
ONE page response with batched SELECTs — the "Вузы" table rendered "—"
because the endpoint returned only the flat university row and the frontend
stubbed the rest.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (register canon metadata)
from app.db.base import Base
from app.models.catalog import (
    ITDirection,
    ITProgram,
    Responsible,
    University,
    UniversityResponsible,
)
from app.models.interactions import InteractionNote, Meeting, UniversityProgram
from app.models.workflow_instances import InstanceStage, WorkflowInstance, WorkflowTask
from app.modules.catalog import service as catalog_service
from app.modules.catalog.repository import list_university_stage_names

import pytest


@pytest.fixture()
def db():
    from sqlalchemy import text

    eng = create_engine("sqlite://")
    Base.metadata.create_all(
        eng,
        tables=[
            University.__table__,
            ITDirection.__table__,
            ITProgram.__table__,
            Responsible.__table__,
            UniversityResponsible.__table__,
            UniversityProgram.__table__,
            Meeting.__table__,
            InteractionNote.__table__,
            WorkflowInstance.__table__,
            WorkflowTask.__table__,
        ],
    )
    # InstanceStage DDL uses DEFERRABLE INITIALLY DEFERRED (PostgreSQL-only),
    # so create an equivalent table manually for sqlite unit tests.
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS instance_stages ("
            "instance_id CHAR(32) NOT NULL, template_stage_id CHAR(32), responsible_id CHAR(32), "
            "order_index INTEGER NOT NULL, name VARCHAR(512) NOT NULL, "
            "description TEXT, is_required BOOLEAN NOT NULL DEFAULT 1, "
            "status VARCHAR(32) NOT NULL DEFAULT 'pending', due_date DATE, started_at DATETIME, "
            "completed_at DATETIME, id CHAR(32) NOT NULL PRIMARY KEY, "
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, "
            "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, "
            "UNIQUE (instance_id, order_index), "
            "FOREIGN KEY(instance_id) REFERENCES workflow_instances (id) "
            "ON DELETE CASCADE)"
        ))
    with Session(eng) as session:
        yield session
    eng.dispose()


def _seed(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    direction = ITDirection(id=uuid.uuid4(), code="SEC", name="Информационная безопасность")
    prog1 = ITProgram(id=uuid.uuid4(), direction_id=direction.id, name="Информационная безопасность")
    prog2 = ITProgram(id=uuid.uuid4(), direction_id=direction.id, name="DevOps")
    resp = Responsible(full_name="Иванов Иван", email="ivanov@example.ru", role="Куратор")
    full = University(name="Московский технический университет", city="Москва")
    empty = University(name="Пустой вуз", city="Казань")
    db.add_all([direction, prog1, prog2, resp, full, empty])
    db.flush()
    db.add(UniversityResponsible(
        university_id=full.id, responsible_id=resp.id, is_primary=True,
    ))
    db.add_all([
        UniversityProgram(university_id=full.id, program_id=prog1.id, status="active"),
        UniversityProgram(university_id=full.id, program_id=prog2.id, status="planned"),
    ])
    db.add(Meeting(
        university_id=full.id, meeting_type="online", subject="Созвон",
        participants=[], meeting_at=now - timedelta(days=1),
        created_by_keycloak_sub="tester",
    ))
    db.add(InteractionNote(
        university_id=full.id, author_keycloak_sub="tester", content="Заметка",
    ))
    db.flush()
    inst = WorkflowInstance(
        university_id=full.id, template_id=uuid.uuid4(), status="active",
    )
    db.add(inst)
    db.flush()
    stage = InstanceStage(
        instance_id=inst.id, order_index=1, name="Согласование программы",
        status="current", due_date=date.today() - timedelta(days=2),
    )
    db.add(stage)
    db.flush()
    inst.current_instance_stage_id = stage.id
    db.commit()
    return {"full": full.id, "empty": empty.id}


def test_list_returns_presentation_aggregates(db):
    ids = _seed(db)
    items, total = catalog_service.list_university_page(
        db, page=1, page_size=20, search=None, city=None, responsible_id=None,
        sort_by="name", sort_order="asc",
    )
    assert total == 2
    by_id = {i.id: i for i in items}

    full = by_id[ids["full"]]
    assert full.responsible is not None
    assert full.responsible.full_name == "Иванов Иван"
    assert full.programs_count == 2
    assert full.program_status_counts == {"active": 1, "planned": 1}
    assert full.current_stage is not None
    assert full.current_stage.name == "Согласование программы"
    assert full.last_interaction_at is not None
    assert full.attention is True  # overdue open stage (due 2 days ago)

    empty = by_id[ids["empty"]]
    assert empty.responsible is None
    assert empty.programs_count == 0
    assert empty.program_status_counts == {}
    assert empty.current_stage is None
    assert empty.last_interaction_at is None
    assert empty.attention is False


def test_list_empty_db_returns_empty_page(db):
    items, total = catalog_service.list_university_page(
        db, page=1, page_size=20, search=None, city=None, responsible_id=None,
        sort_by="name", sort_order="asc",
    )
    assert total == 0
    assert items == []


def test_current_stage_filter_applies_before_pagination(db):
    ids = _seed(db)
    assert list_university_stage_names(db) == ["Согласование программы"]

    items, total = catalog_service.list_university_page(
        db, page=1, page_size=1, search="Московский", city=None,
        responsible_id=None, sort_by="name", sort_order="asc",
        workflow_stage="Согласование программы",
    )
    assert total == 1
    assert [item.id for item in items] == [ids["full"]]

    items, total = catalog_service.list_university_page(
        db, page=1, page_size=1, search=None, city=None,
        responsible_id=None, sort_by="name", sort_order="asc",
        workflow_stage="Несуществующий этап",
    )
    assert total == 0
    assert items == []


def test_multiple_cities_and_stages_filter_before_pagination(db):
    ids = _seed(db)
    second = WorkflowInstance(
        university_id=ids["empty"], template_id=uuid.uuid4(), status="active",
    )
    db.add(second)
    db.flush()
    stage = InstanceStage(
        instance_id=second.id, order_index=1, name="Запуск", status="current",
    )
    db.add(stage)
    db.flush()
    second.current_instance_stage_id = stage.id
    db.commit()

    first_page, total = catalog_service.list_university_page(
        db, page=1, page_size=1, search=None, city=["Москва", "Казань"],
        responsible_id=None, sort_by="name", sort_order="asc",
        workflow_stage=["Согласование программы", "Запуск"],
    )
    second_page, second_total = catalog_service.list_university_page(
        db, page=2, page_size=1, search=None, city=["Москва", "Казань"],
        responsible_id=None, sort_by="name", sort_order="asc",
        workflow_stage=["Согласование программы", "Запуск"],
    )
    assert total == second_total == 2
    assert {first_page[0].id, second_page[0].id} == {ids["full"], ids["empty"]}

    only_kazan, total = catalog_service.list_university_page(
        db, page=1, page_size=1, search=None, city=["Казань"],
        responsible_id=None, sort_by="name", sort_order="asc",
        workflow_stage=["Согласование программы", "Запуск"],
    )
    assert total == 1
    assert [item.id for item in only_kazan] == [ids["empty"]]
