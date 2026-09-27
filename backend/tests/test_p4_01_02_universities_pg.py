"""P4-01-02 PostgreSQL tests: UnifiedFilter wired into GET /api/v1/universities.

Legacy P1 query params (search/city/responsible_id/region/sort/page) stay
backward-compatible; the frozen UnifiedFilter dimensions are additive (AND).
Pagination totals reflect the filtered result; EXISTS predicates never
duplicate universities.

Requires ``TEST_DATABASE_URL=postgresql+psycopg://...`` (skipped otherwise).
"""

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.models  # noqa: F401 (register metadata)
from app.config import settings
from app.db.session import get_db
from app.main import app
from app.models.catalog import (
    ITDirection,
    ITProgram,
    Responsible,
    University,
    UniversityResponsible,
)
from app.models.interactions import Meeting, UniversityProduct, UniversityProgram
from app.models.catalog import ITProduct, Vendor

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def engine():
    from tests.db_helpers import require_pg_engine

    eng = require_pg_engine(TEST_URL)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    with Session(engine) as session:
        ids = _seed(session)
        session.commit()
        yield session, ids


@pytest.fixture()
def client(engine):
    def _override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _override
    old = settings.auth_dev_bypass
    settings.auth_dev_bypass = True
    _seed_ids = {}
    with Session(engine) as session:
        for key, value in _seed(session).items():
            _seed_ids[key] = value
        session.commit()
    c = TestClient(app)
    try:
        yield c, _seed_ids
    finally:
        app.dependency_overrides.pop(get_db, None)
        settings.auth_dev_bypass = old


def _seed(s: Session) -> dict:
    d1 = ITDirection(id=uuid4(), code="D1", name="Direction One")
    d2 = ITDirection(id=uuid4(), code="D2", name="Direction Two")
    p1 = ITProgram(id=uuid4(), direction_id=d1.id, name="Program 1")
    p2 = ITProgram(id=uuid4(), direction_id=d1.id, name="Program 2")
    p3 = ITProgram(id=uuid4(), direction_id=d2.id, name="Program 3")
    vendor = Vendor(id=uuid4(), name="Vendor V")
    prod1 = ITProduct(id=uuid4(), vendor_id=vendor.id, name="Product 1")
    prod2 = ITProduct(id=uuid4(), vendor_id=vendor.id, name="Product 2")
    r1 = Responsible(id=uuid4(), full_name="Resp One", email="r1@x.local")
    r2 = Responsible(id=uuid4(), full_name="Resp Two", email="r2@x.local")
    alpha = University(id=uuid4(), name="Uni Alpha", city="Moscow",
                       created_at=_utc(2026, 1, 10))
    beta = University(id=uuid4(), name="Uni Beta", city="SPb",
                      created_at=_utc(2026, 5, 20))
    gamma = University(id=uuid4(), name="Uni Gamma", city="Moscow",
                       created_at=_utc(2026, 8, 1))
    s.add_all(
        [d1, d2, p1, p2, p3, vendor, prod1, prod2, r1, r2, alpha, beta, gamma]
    )
    s.flush()
    s.add_all(
        [
            UniversityProgram(university_id=alpha.id, program_id=p1.id),
            UniversityProgram(university_id=alpha.id, program_id=p2.id),
            UniversityProgram(university_id=beta.id, program_id=p3.id),
            UniversityProduct(university_id=alpha.id, product_id=prod1.id),
            UniversityProduct(university_id=beta.id, product_id=prod2.id),
            UniversityResponsible(university_id=alpha.id, responsible_id=r1.id),
            UniversityResponsible(university_id=alpha.id, responsible_id=r2.id),
            UniversityResponsible(university_id=beta.id, responsible_id=r2.id),
        ]
    )
    # The ТЗ period filters on interaction dates, so the list endpoint needs
    # real interactions to select by month.
    s.add_all([
        Meeting(id=uuid4(), university_id=u.id, meeting_type="online",
                subject=f"Meeting {n}", participants=[],
                meeting_at=at, created_by_keycloak_sub="t")
        for n, (u, at) in enumerate((
            (alpha, _utc(2026, 1, 20)),
            (beta, _utc(2026, 4, 10)),
            (gamma, _utc(2026, 8, 5)),
        ))
    ])
    return {
        "d1": d1.id, "d2": d2.id,
        "p1": p1.id, "p2": p2.id, "p3": p3.id,
        "prod1": prod1.id, "prod2": prod2.id,
        "r1": r1.id, "r2": r2.id,
        "alpha": alpha.id, "beta": beta.id, "gamma": gamma.id,
    }


def _names(body: dict) -> list[str]:
    return [item["name"] for item in body["items"]]


# ------------------------------------------------------- legacy preserved


def test_legacy_list_unchanged_without_unified_params(client):
    c, _ = client
    r = c.get("/api/v1/universities", params={"page": 1, "page_size": 20})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 3
    assert _names(body) == ["Uni Alpha", "Uni Beta", "Uni Gamma"]


def test_legacy_city_filter_still_works(client):
    c, _ = client
    r = c.get("/api/v1/universities", params={"city": "Moscow"})
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 2


def test_legacy_responsible_id_filter_still_works(client):
    c, ids = client
    r = c.get("/api/v1/universities", params={"responsible_id": str(ids["r2"])})
    assert r.status_code == 200, r.text
    assert sorted(_names(r.json())) == ["Uni Alpha", "Uni Beta"]


def test_legacy_region_deprecated_noop(client):
    c, _ = client
    r = c.get("/api/v1/universities", params={"region": "anything"})
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 3


def test_legacy_search_and_sort_still_work(client):
    c, _ = client
    r = c.get(
        "/api/v1/universities",
        params={"search": "beta", "sort_by": "name", "sort_order": "desc"},
    )
    assert r.status_code == 200, r.text
    assert _names(r.json()) == ["Uni Beta"]


# ------------------------------------------------------- unified additive


def test_unified_university_ids_filter(client):
    c, ids = client
    r = c.get(
        "/api/v1/universities",
        params=[("university_ids", str(ids["alpha"])), ("university_ids", str(ids["beta"]))],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert _names(body) == ["Uni Alpha", "Uni Beta"]


def test_unified_direction_ids_no_duplicates(client):
    c, ids = client
    # Alpha matches via 2 programs of d1 AND 2 responsibles -> still 1 row.
    r = c.get("/api/v1/universities", params={"direction_ids": str(ids["d1"])})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert _names(body) == ["Uni Alpha"]


def test_unified_program_and_product_ids(client):
    c, ids = client
    r = c.get("/api/v1/universities", params={"program_ids": str(ids["p3"])})
    assert r.status_code == 200, r.text
    assert _names(r.json()) == ["Uni Beta"]
    r = c.get("/api/v1/universities", params={"product_ids": str(ids["prod1"])})
    assert r.status_code == 200, r.text
    assert _names(r.json()) == ["Uni Alpha"]


def test_unified_responsible_ids_no_duplicates(client):
    c, ids = client
    r = c.get("/api/v1/universities", params={"responsible_ids": str(ids["r2"])})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert _names(body) == ["Uni Alpha", "Uni Beta"]


def test_unified_and_legacy_combine_with_and(client):
    c, ids = client
    r = c.get(
        "/api/v1/universities",
        params={"city": "Moscow", "direction_ids": str(ids["d1"])},
    )
    assert r.status_code == 200, r.text
    assert _names(r.json()) == ["Uni Alpha"]
    r = c.get(
        "/api/v1/universities",
        params={"city": "SPb", "direction_ids": str(ids["d1"])},
    )
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 0


def test_unified_date_range_on_interactions(client):
    """ТЗ: the list endpoint applies the same interaction period as reports."""
    c, _ = client
    r = c.get(
        "/api/v1/universities",
        params={"date_from": "2026-02-01", "date_to": "2026-06-01"},
    )
    assert r.status_code == 200, r.text
    assert _names(r.json()) == ["Uni Beta"]


def test_unified_reversed_range_is_422(client):
    c, _ = client
    r = c.get(
        "/api/v1/universities",
        params={"date_from": "2026-06-01", "date_to": "2026-01-01"},
    )
    assert r.status_code == 422, r.text


def test_unified_invalid_uuid_is_422(client):
    c, _ = client
    r = c.get("/api/v1/universities", params={"university_ids": "not-a-uuid"})
    assert r.status_code == 422, r.text


# ------------------------------------------------------- pagination


def test_pagination_total_reflects_unified_filter(client):
    c, ids = client
    r = c.get(
        "/api/v1/universities",
        params={
            "responsible_ids": str(ids["r2"]),
            "page": 1,
            "page_size": 1,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2  # filtered total, not the unfiltered count
    assert len(body["items"]) == 1
    r2 = c.get(
        "/api/v1/universities",
        params={
            "responsible_ids": str(ids["r2"]),
            "page": 2,
            "page_size": 1,
        },
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["total"] == 2
    assert _names(body) != _names(r2.json())  # disjoint pages


# ------------------------------------------------------- openapi


def test_openapi_lists_unified_params(client):
    c, _ = client
    spec = c.get("/openapi.json")
    assert spec.status_code == 200
    params = {
        p["name"]
        for p in spec.json()["paths"]["/api/v1/universities"]["get"].get(
            "parameters", []
        )
    }
    assert {
        "date_from",
        "date_to",
        "university_ids",
        "direction_ids",
        "program_ids",
        "product_ids",
        "responsible_ids",
        "workflow_statuses",
        "city",
        "responsible_id",
        "region",
        "search",
        "page",
        "page_size",
    } <= params


def test_report_request_schema_in_openapi():
    from app.modules.analytics.report_request import ReportRequest

    schema = ReportRequest.model_json_schema()
    assert set(schema["properties"]) == {"format", "filters", "columns"}
    fmt = schema["properties"]["format"]
    assert "xlsx" in str(fmt) and "pdf" in str(fmt) and "json" in str(fmt)
