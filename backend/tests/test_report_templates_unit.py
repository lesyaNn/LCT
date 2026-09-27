"""Report templates API (ТЗ §6/§8): save/list/delete over SQLite."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.errors import register_error_handlers
from app.core.security import CurrentUser, get_current_user
from app.db.base import Base
from app.models.report_template import ReportTemplate  # noqa: F401
from app.modules.analytics.report_templates import router
from app.modules.audit.service import get_audit_db


def _client(user: CurrentUser, session_factory) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(router)

    def _db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_audit_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def _session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[ReportTemplate.__table__])
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _admin() -> CurrentUser:
    return CurrentUser(id="admin-1", roles={"admin"})


def _user(uid: str = "u-1") -> CurrentUser:
    return CurrentUser(id=uid, roles={"user"})


def test_create_list_delete_personal_template():
    client = _client(_user(), _session_factory())
    created = client.post(
        "/reports/templates",
        json={"name": "Мой набор", "format": "xlsx", "filters": {}, "columns": ["university"]},
    )
    assert created.status_code == 201, created.text
    tpl_id = created.json()["id"]
    listed = client.get("/reports/templates")
    assert listed.status_code == 200
    assert [t["id"] for t in listed.json()] == [tpl_id]
    assert client.delete(f"/reports/templates/{tpl_id}").status_code == 204
    assert client.get("/reports/templates").json() == []


def test_shared_requires_admin_and_visible_to_others():
    admin_factory = _session_factory()
    admin = _client(_admin(), admin_factory)
    created = admin.post(
        "/reports/templates",
        json={"name": "Общий", "format": "pdf", "filters": {}, "columns": None, "is_shared": True},
    )
    assert created.status_code == 201, created.text
    assert created.json()["is_shared"] is True
    # Non-admin cannot create shared templates.
    denied = _client(_user(), admin_factory).post(
        "/reports/templates",
        json={"name": "X", "format": "xlsx", "filters": {}, "is_shared": True},
    )
    assert denied.status_code == 403
    # Another user sees the shared template but cannot delete it.
    other = _client(_user("u-2"), admin_factory)
    assert [t["name"] for t in other.get("/reports/templates").json()] == ["Общий"]
    assert other.delete(f"/reports/templates/{created.json()['id']}").status_code == 403


def test_validation_and_404():
    client = _client(_user(), _session_factory())
    bad = client.post(
        "/reports/templates",
        json={"name": "X", "format": "xlsx", "filters": {}, "columns": ["bogus"]},
    )
    assert bad.status_code == 422
    assert client.delete("/reports/templates/00000000-0000-4000-8000-000000000000").status_code == 404
    assert client.delete("/reports/templates/not-a-uuid").status_code == 404
