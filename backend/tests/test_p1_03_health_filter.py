"""P1-03-01: health_status filter + health_score sort on GET /universities.

Scores are computed in Python per candidate university (5-minute cache,
same as GET /health-score); total is AFTER the health filter.
DB integration tests require PostgreSQL via ``TEST_DATABASE_URL``.
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.models  # noqa: F401 (register metadata on Base)
from app.models.catalog import University
from app.modules.health_score.materialization import refresh_health_score

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


def _seed_two(db: Session) -> None:
    rows = []
    for name in (f"Alpha-{_tag()}", f"Beta-{_tag()}"):
        row = University(name=name, city="Moscow")
        db.add(row)
        rows.append(row)
    db.commit()
    for row in rows:
        refresh_health_score(db, row.id, "test")
    db.commit()


def test_health_filter_returns_subset_with_scores(db: Session, client: TestClient):
    _seed_two(db)
    base = client.get("/api/v1/universities", params={"page_size": 100})
    assert base.status_code == 200, base.text
    assert base.json()["total"] >= 2
    # no health computation on the default path
    assert all(i["health_score"] is None for i in base.json()["items"])

    for status in ("green", "yellow", "red"):
        r = client.get("/api/v1/universities", params={"health_status": status})
        assert r.status_code == 200, r.text
        for item in r.json()["items"]:
            assert item["health_status"] == status
            assert isinstance(item["health_score"], int)
    # union of the three filters covers every university
    counts = sum(
        client.get("/api/v1/universities", params={"health_status": s}).json()["total"]
        for s in ("green", "yellow", "red")
    )
    assert counts == base.json()["total"]


def test_health_sort_orders_by_score(db: Session, client: TestClient):
    _seed_two(db)
    desc = client.get(
        "/api/v1/universities",
        params={"sort_by": "health_score", "sort_order": "desc", "page_size": 100},
    )
    assert desc.status_code == 200, desc.text
    scores = [i["health_score"] for i in desc.json()["items"]]
    assert scores == sorted(scores, reverse=True)
    asc = client.get(
        "/api/v1/universities",
        params={"sort_by": "health_score", "sort_order": "asc", "page_size": 100},
    )
    assert [i["health_score"] for i in asc.json()["items"]] == sorted(scores)


def test_health_invalid_status_is_422(client: TestClient):
    r = client.get("/api/v1/universities", params={"health_status": "purple"})
    assert r.status_code == 422, r.text
    r = client.get("/api/v1/universities", params={"sort_by": "health_status"})
    assert r.status_code == 422, r.text
