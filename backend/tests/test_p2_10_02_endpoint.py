"""P2-10-02: endpoint attention-items — HTTP тесты (404/200/сортировка)."""

from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

import app.models  # noqa: F401 (register metadata)
from app.core.security import CurrentUser, get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.catalog import University
from app.models.interactions import Document

TODAY = date(2026, 9, 20)


@pytest.fixture()
def client(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/att.db")

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_conn, _rec):  # pragma: no cover
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(eng)

    def _override():
        with Session(eng) as session:
            yield session

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="test-sub", roles={"admin"}
    )
    with Session(eng) as session:
        uni = University(id=uuid4(), name="Вуз Att-1")
        session.add(uni)
        session.flush()
        session.add(Document(
            id=uuid4(), university_id=uni.id, document_type="act",
            title="Акт", file_path="/f", file_name="a.pdf",
            status_raw="signed", expires_at=TODAY - timedelta(days=1),
            uploaded_by_keycloak_sub="t"))
        session.commit()
        uni_id = uni.id
    try:
        yield TestClient(app, raise_server_exceptions=False), uni_id
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        eng.dispose()


def test_404_unknown_university(client):
    http, _ = client
    assert http.get(f"/api/v1/universities/{uuid4()}/attention-items").status_code == 404


def test_200_items_sorted_and_cached(client):
    http, uni_id = client
    first = http.get(f"/api/v1/universities/{uni_id}/attention-items")
    assert first.status_code == 200, first.text
    items = first.json()["items"]
    assert len(items) == 1
    assert items[0]["code"] == "EXPIRED_DOCUMENT"
    assert items[0]["severity"] == "high"
    second = http.get(f"/api/v1/universities/{uni_id}/attention-items")
    assert second.status_code == 200
    assert second.json() == first.json()
