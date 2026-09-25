"""Dev-1 filter adapter tests (P4-07-01/P4-09-01 provider wiring).

Pure-unit ``normalize`` runs everywhere; ``select`` consistency runs on
sqlite (selected tables only — the full metadata has PG-only DDL) and on
PostgreSQL (``test_dev1_provider_pg_consistency``, needs
``TEST_DATABASE_URL``): the provider university set always equals
``AnalyticsService.filtered_university_ids`` for the same filter.
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.modules.analytics.dev1_provider import Dev1FilterProvider, provider


def test_provider_version_and_normalize_empty():
    assert provider.version == "dev1-unified-v1"
    assert provider.normalize({}) == {
        "date_from": None, "date_to": None, "university_ids": [],
        "direction_ids": [], "program_ids": [], "product_ids": [],
        "responsible_ids": [], "workflow_statuses": [],
    }


def test_normalize_rejects_unknown_fields_422():
    with pytest.raises(HTTPException) as exc_info:
        provider.normalize({"bogus": 1})
    assert exc_info.value.status_code == 422


def test_normalize_rejects_bad_range_422():
    with pytest.raises(HTTPException) as exc_info:
        provider.normalize({"date_from": "2026-12-31", "date_to": "2026-01-01"})
    assert exc_info.value.status_code == 422


def _sqlite_db():
    from app.models.catalog import (
        ITDirection,
        ITProgram,
        University,
        UniversityResponsible,
    )
    from app.models.interactions import UniversityProgram
    from app.models.workflow_instances import WorkflowInstance

    eng = create_engine("sqlite://")
    for table in (
        University.__table__, ITDirection.__table__, ITProgram.__table__,
        UniversityProgram.__table__, UniversityResponsible.__table__,
        WorkflowInstance.__table__,
    ):
        table.create(eng)
    return eng


def _seed_sqlite(db: Session) -> dict:
    from app.models.catalog import ITDirection, ITProgram, University
    from app.models.interactions import UniversityProgram

    ua = University(id=uuid.uuid4(), name="Альфа")
    ub = University(id=uuid.uuid4(), name="Бета")
    da = ITDirection(id=uuid.uuid4(), code="cs", name="ИВТ")
    db_ = ITDirection(id=uuid.uuid4(), code="is", name="ИБ")
    pa = ITProgram(id=uuid.uuid4(), direction_id=da.id, name="ИИ")
    pb = ITProgram(id=uuid.uuid4(), direction_id=db_.id, name="ИБ")
    db.add_all([ua, ub, da, db_, pa, pb])
    db.flush()
    db.add_all([
        UniversityProgram(university_id=ua.id, program_id=pa.id, status="active"),
        UniversityProgram(university_id=ub.id, program_id=pb.id, status="active"),
    ])
    db.commit()
    return {"ua": ua.id, "ub": ub.id, "pa": pa.id, "pb": pb.id,
            "da": da.id, "db": db_.id}


def test_select_empty_filter_returns_all():
    eng = _sqlite_db()
    with Session(eng) as db:
        ids = _seed_sqlite(db)
        sel = provider.select(db, {})
        assert set(sel.university_ids) == {ids["ua"], ids["ub"]}
        assert set(sel.program_ids) == {ids["pa"], ids["pb"]}
        assert sel.license_ids is None
        assert sel.workflow_instance_ids is None


def test_select_university_ids_narrows():
    eng = _sqlite_db()
    with Session(eng) as db:
        ids = _seed_sqlite(db)
        sel = provider.select(db, {"university_ids": [str(ids["ua"])]})
        assert sel.university_ids == [ids["ua"]]


def test_select_program_ids_pass_through_and_match_service():
    from app.modules.analytics.analytics import AnalyticsService
    from app.modules.analytics.filters import UnifiedFilter

    eng = _sqlite_db()
    with Session(eng) as db:
        ids = _seed_sqlite(db)
        dto = UnifiedFilter.model_validate({"program_ids": [str(ids["pa"])]})
        sel = provider.select(db, {"program_ids": [str(ids["pa"])]})
        assert sel.program_ids == [ids["pa"]]
        # One filter -> one university set (list/dataset/analytics identical).
        assert set(sel.university_ids) == set(
            AnalyticsService.filtered_university_ids(db, dto)
        )
        assert sel.university_ids == [ids["ua"]]


def test_select_workflow_statuses_narrow_instances():
    eng = _sqlite_db()
    with Session(eng) as db:
        _seed_sqlite(db)
        # Инстансов нет: EXISTS не срабатывает — пусто везде (fail closed).
        sel = provider.select(db, {"workflow_statuses": ["current"]})
        assert sel.university_ids == []
        assert sel.workflow_instance_ids == []


def test_select_direction_ids_narrow_programs():
    eng = _sqlite_db()
    with Session(eng) as db:
        ids = _seed_sqlite(db)
        sel = provider.select(db, {"direction_ids": [str(ids["da"])]})
        assert sel.program_ids == [ids["pa"]]
        assert sel.university_ids == [ids["ua"]]


@pytest.fixture()
def pg_engine():
    from tests.db_helpers import require_pg_engine

    eng = require_pg_engine(os.getenv("TEST_DATABASE_URL", "sqlite://"))
    yield eng
    eng.dispose()


def test_dev1_provider_pg_consistency(pg_engine):
    """Provider university set == service set == dataset set (PG, real SQL)."""
    from app.modules.analytics.analytics import AnalyticsService
    from app.modules.analytics.dataset import ReportDatasetService
    from app.modules.analytics.filters import UnifiedFilter
    from app.models.catalog import ITDirection, ITProgram, University
    from app.models.interactions import UniversityProgram

    eng = pg_engine
    with Session(eng) as db:
        da = ITDirection(id=uuid.uuid4(), code="cs-p", name="ИВТ-П")
        ua = University(id=uuid.uuid4(), name="Альфа-П")
        ub = University(id=uuid.uuid4(), name="Бета-П")
        pa = ITProgram(id=uuid.uuid4(), direction_id=da.id, name="ИИ-П")
        db.add_all([da, ua, ub, pa])
        db.flush()
        db.add(UniversityProgram(
            university_id=ua.id, program_id=pa.id, status="active"))
        db.commit()

        raw = {"program_ids": [str(pa.id)]}
        dto = UnifiedFilter.model_validate(raw)
        via_provider = provider.select(db, raw)
        via_service = AnalyticsService.filtered_university_ids(db, dto)
        ds = ReportDatasetService.fetch_rows(db, dto, ["university"])
        assert set(via_provider.university_ids) == set(via_service) == {ua.id}
        assert {r["university"] for r in ds.rows} == {"Альфа-П"}
        assert ds.university_ids == {ua.id}


def test_dev1_provider_is_loadable_via_env(monkeypatch):
    from app.modules.analytics.integration import get_filter_provider, load_object

    monkeypatch.setenv(
        "P4_FILTER_PROVIDER", "app.modules.analytics.dev1_provider:provider")
    assert isinstance(load_object("P4_FILTER_PROVIDER"), Dev1FilterProvider)
    assert get_filter_provider().version == "dev1-unified-v1"
