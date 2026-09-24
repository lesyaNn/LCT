"""P2-08-03: ranking endpoint — HTTP тесты (сортировка, фильтр, пагинация)."""

import os
from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.models  # noqa: F401 (register metadata)
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.main import app
from app.models.catalog import University
from app.models.interactions import Document
from app.modules.health_score.materialization import refresh_health_score

TODAY = date(2026, 9, 20)

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")


@pytest.fixture()
def client():
    from tests.db_helpers import require_pg_engine

    eng = require_pg_engine(TEST_URL)

    def _override():
        with Session(eng) as session:
            yield session

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="test-sub", roles={"admin"}
    )
    with Session(eng) as session:
        good = University(id=uuid4(), name="Вуз R-good")
        bad = University(id=uuid4(), name="Вуз R-bad")
        session.add_all([good, bad])
        session.flush()
        # bad: 2 обязательных документа, оба просрочены → D=0 → score<100
        for i in range(2):
            session.add(Document(
                id=uuid4(), university_id=bad.id, document_type="contract",
                title=f"Договор {i}", file_path="/f", file_name="d.pdf",
                status_raw="signed", expires_at=TODAY - timedelta(days=1),
                uploaded_by_keycloak_sub="t"))
        session.commit()
        refresh_health_score(session, good.id, "test")
        refresh_health_score(session, bad.id, "test")
        session.commit()
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        eng.dispose()


def test_ranking_sorted_and_ranked(client):
    r = client.get("/api/v1/health-score/ranking")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    items = body["items"]
    assert items[0]["score"] >= items[1]["score"]
    assert items[0]["rank"] == 1
    assert items[1]["rank"] == 2
    assert items[0]["university_name"] == "Вуз R-good"
    assert items[0]["status"] == "green"


def test_ranking_status_filter_and_pagination(client):
    r = client.get("/api/v1/health-score/ranking?status=green")
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["status"] == "green"
    r = client.get("/api/v1/health-score/ranking?limit=1&offset=1")
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1
    assert r.json()["items"][0]["rank"] == 2
    assert r.json()["total"] == 2
