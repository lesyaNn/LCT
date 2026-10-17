"""Focused map data checks without a live CRM database."""

import json
import uuid
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.models  # noqa: F401
from app.core.security import CurrentUser
from app.db.base import Base
from app.models.catalog import ITDirection, ITProgram, University
from app.models.interactions import UniversityProgram
from app.models.workflow_instances import WorkflowInstance
from app.modules.analytics.filters import UnifiedFilter
from app.modules.catalog.repository import list_universities_map
from app.modules.universities.city_region import city_region_code
from app.modules.catalog import router as catalog_router_module, service as catalog_service
from app.modules.audit.service import get_audit_db


def test_city_region_uses_exact_unambiguous_geonames_codes():
    assert city_region_code("Москва") == "RU.48"
    assert city_region_code("Ростов-на-Дону") == "RU.61"
    assert city_region_code("Екатеринбург") == "RU.71"
    assert city_region_code("Киров") is None
    assert city_region_code("Несуществующий город") is None


def test_geometry_has_matching_regions_and_license_metadata():
    path = Path(__file__).resolve().parents[2] / "frontend/public/maps/russia-regions.json"
    geometry = json.loads(path.read_text(encoding="utf-8"))
    regions = {item["code"]: item for item in geometry["regions"]}
    assert len(regions) >= 80
    assert regions["RU.48"]["name"] == "Москва"
    assert regions["RU.61"]["name"] == "Ростовская область"
    assert all(item["path"].startswith("M") for item in regions.values())
    assert "naturalearthdata.com" in geometry["license"]


def test_map_selection_reuses_filters_statuses_and_security_scope():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[
        University.__table__, ITDirection.__table__, ITProgram.__table__,
        UniversityProgram.__table__, WorkflowInstance.__table__,
    ])
    try:
        with Session(engine) as db:
            own = University(name="Свой вуз", city="Москва")
            foreign = University(name="Чужой вуз", city="Ростов-на-Дону")
            unknown = University(name="Без города", city="Неизвестный город")
            direction = ITDirection(code="map-test", name="Направление")
            db.add_all([own, foreign, unknown, direction])
            db.flush()
            program = ITProgram(direction_id=direction.id, name="Программа", description="")
            db.add(program)
            db.flush()
            db.add_all([
                UniversityProgram(university_id=own.id, program_id=program.id, status="launched"),
                UniversityProgram(university_id=foreign.id, program_id=program.id, status="planned"),
                WorkflowInstance(university_id=own.id, template_id=uuid.uuid4(), status="active"),
                WorkflowInstance(university_id=foreign.id, template_id=uuid.uuid4(), status="completed"),
            ])
            db.flush()
            user = CurrentUser(id="reader", roles={"user"}, university_ids=(str(own.id), str(unknown.id)))
            rows = list_universities_map(db, search=None, city=None, responsible_id=None, user=user)
            assert [row["name"] for row in rows] == ["Без города", "Свой вуз"]
            assert rows[0]["region_code"] is None
            assert rows[1]["region_code"] == "RU.48"
            assert rows[1]["launched_programs"] == 1
            assert rows[1]["active_workflow"] is True
            assert rows[0]["launched_programs"] == 0

            filtered = list_universities_map(db, search=None, city=["Москва"], responsible_id=None,
                                             unified_filter=UnifiedFilter(program_ids=[program.id]), user=user)
            assert [row["id"] for row in filtered] == [own.id]
            assert list_universities_map(db, search="Чужой", city=None, responsible_id=None, user=user) == []
            assert list_universities_map(db, search=None, city=None, responsible_id=None,
                                         user=CurrentUser(id="unassigned", roles={"user"})) == []
    finally:
        engine.dispose()


def test_map_http_route_binds_shared_filters_and_serializes(monkeypatch):
    captured = {}
    identifier = uuid.uuid4()

    def fake_map(_db, **filters):
        captured.update(filters)
        return [{"id": identifier, "name": "Вуз", "city": "Москва", "region_code": "RU.48",
                 "programs_count": 1, "launched_programs": 1, "active_programs": 0, "active_workflow": True}]

    monkeypatch.setattr(catalog_service, "list_university_map", fake_map)
    app = FastAPI()
    app.include_router(catalog_router_module.router, prefix="/api/v1")
    app.dependency_overrides[catalog_router_module.READ] = lambda: CurrentUser(id="admin", roles={"admin"})
    app.dependency_overrides[get_audit_db] = lambda: object()
    response = TestClient(app).get(f"/api/v1/universities/map?city=Москва&program_ids={identifier}")
    assert response.status_code == 200
    assert response.json()[0]["region_code"] == "RU.48"
    assert captured["city"] == ["Москва"]
    assert captured["unified_filter"].program_ids == [identifier]
