"""P5 RBAC matrix for mounted university routes on migrated PostgreSQL 16."""

import os
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.main import app
from app.models.catalog import University
from app.schemas.errors import ErrorResponse


@pytest.fixture()
def context():
    from tests.db_helpers import require_pg_engine

    engine = require_pg_engine(os.getenv("TEST_DATABASE_URL", "sqlite://"))
    a, b, c = uuid4(), uuid4(), uuid4()
    with Session(engine) as db:
        db.add_all([
            University(id=a, name="Private Alpha"),
            University(id=b, name="Private Beta"),
            University(id=c, name="Private Gamma"),
        ])
        db.commit()

    current = {"user": CurrentUser(id="p5", roles={"user"}, university_ids=(str(b),))}

    def db_override():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    try:
        with TestClient(app) as client:
            yield client, current, a, b, c
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        engine.dispose()


def _as(current, role, ids=None):
    current["user"] = CurrentUser(id="p5", roles={role}, university_ids=ids)


def _forbidden(response):
    assert response.status_code == 403, response.text
    body = ErrorResponse.model_validate(response.json())
    assert body.error.code == "FORBIDDEN"
    assert body.error.details == {}
    assert UUID(response.headers["X-Request-ID"]) == body.error.request_id
    assert "Private" not in response.text


def test_university_collection_detail_and_mutation_matrix(context):
    client, current, a, b, c = context
    path = "/api/v1/universities"

    response = client.get(path)
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert {row["id"] for row in response.json()["items"]} == {str(b)}
    response = client.get(path, params={"university_ids": str(a)})
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0
    assert client.get(f"{path}/{b}").status_code == 200
    _forbidden(client.get(f"{path}/{a}"))
    _forbidden(client.post(path, json={"name": "Denied"}))
    _forbidden(client.patch(f"{path}/{b}", json={"name": "Denied"}))
    _forbidden(client.get(f"{path}/{a}/passport"))

    _as(current, "manager", (str(b),))
    assert client.get(path).json()["total"] == 1
    assert client.patch(f"{path}/{b}", json={"name": "Scoped Manager"}).status_code == 200
    _forbidden(client.patch(f"{path}/{a}", json={"name": "Denied"}))
    _forbidden(client.post(path, json={"name": "Denied"}))
    _forbidden(client.get(f"{path}/{a}"))

    _as(current, "manager")
    assert client.get(path).json()["total"] == 0
    _forbidden(client.get(f"{path}/{b}"))

    _as(current, "admin")
    assert client.get(path).json()["total"] == 3
    assert client.get(f"{path}/{a}").status_code == 200
    assert client.patch(f"{path}/{a}", json={"name": "Admin Update"}).status_code == 200
    assert client.post(path, json={"name": "Admin Created"}).status_code == 201
