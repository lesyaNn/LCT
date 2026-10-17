"""Admin Users integration tests with an in-memory Keycloak Admin API seam."""

import os
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.catalog import University
from app.modules.admin_users.keycloak_client import get_keycloak_admin_client
from app.modules.audit.models import AuditEvent

ADMIN_ID = "00000000-0000-4000-8000-000000000001"
USER_ID = "00000000-0000-4000-8000-000000000002"
SECOND_ADMIN_ID = "00000000-0000-4000-8000-000000000003"
MANAGER_ID = "00000000-0000-4000-8000-000000000004"
FOREIGN_USER_ID = "00000000-0000-4000-8000-000000000005"
EMPTY_USER_ID = "00000000-0000-4000-8000-000000000006"


class FakeKeycloak:
    def __init__(self):
        self.records = {
            ADMIN_ID: {"id": ADMIN_ID, "username": "admin", "email": "admin@example.test", "enabled": True,
                       "firstName": "Тест", "lastName": "Админ", "attributes": {}},
            USER_ID: {"id": USER_ID, "username": "user", "email": "user@example.test", "enabled": True,
                      "firstName": "Тест", "lastName": "Пользователь", "attributes": {}},
        }
        self.roles = {ADMIN_ID: {"admin"}, USER_ID: {"user"}}
        self.logged_out = []
        self.fail_role_remove = False
        self.fail_email = False
        self.ignore_attributes = False

    def users(self, *, search="", first=0, maximum=100):
        found = [row for row in self.records.values() if search.casefold() in
                 " ".join(str(row.get(key) or "") for key in ("firstName", "lastName", "username", "email")).casefold()]
        return deepcopy(found[first:first + maximum])

    def users_count(self, *, search=""):
        return len(self.users(search=search, maximum=10_000))

    def user(self, user_id):
        return deepcopy(self.records[user_id])

    def role(self, name):
        return {"id": name, "name": name}

    def role_users(self, name, first=0, maximum=100):
        ids = [uid for uid, values in self.roles.items() if name in values]
        return [deepcopy(self.records[uid]) for uid in ids[first:first + maximum]]

    def user_roles(self, user_id):
        return [self.role(name) for name in self.roles[user_id]]

    def assign_role(self, user_id, role):
        self.roles[user_id].add(role["name"])

    def remove_role(self, user_id, role):
        if self.fail_role_remove:
            self.fail_role_remove = False
            raise RuntimeError("provider unavailable")
        self.roles[user_id].remove(role["name"])

    def update_user(self, user_id, payload):
        next_record = deepcopy(payload)
        if self.ignore_attributes:
            next_record["attributes"] = deepcopy(self.records[user_id].get("attributes", {}))
        self.records[user_id] = next_record

    def create_user(self, payload):
        if any(row["username"] == payload["username"] or row["email"] == payload["email"]
               for row in self.records.values()):
            from app.core.errors import ConflictError
            raise ConflictError(field="email")
        uid = f"00000000-0000-4000-8000-{len(self.records) + 10:012d}"
        self.records[uid] = {"id": uid, **deepcopy(payload)}
        self.roles[uid] = set()
        return uid

    def delete_user(self, user_id):
        self.records.pop(user_id)
        self.roles.pop(user_id)

    def logout(self, user_id):
        self.logged_out.append(user_id)

    def execute_actions_email(self, user_id, actions):
        if self.fail_email:
            from app.core.errors import BusinessException
            from app.schemas.errors import ErrorCode
            raise BusinessException(ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE)
        assert actions == ["UPDATE_PASSWORD"]

    def ensure_scope_mapper(self):
        pass


@pytest.fixture()
def context():
    from app.main import app
    from app.db import session as db_session
    from tests.db_helpers import require_pg_engine

    engine = require_pg_engine(os.getenv("TEST_DATABASE_URL", "sqlite://"))
    old_bind = db_session.SessionLocal.kw["bind"]
    db_session.SessionLocal.configure(bind=engine)
    kc = FakeKeycloak()
    actor = CurrentUser(id=ADMIN_ID, roles={"admin"}, username="admin")

    def _db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: actor
    app.dependency_overrides[get_keycloak_admin_client] = lambda: kc
    try:
        yield TestClient(app, raise_server_exceptions=False), kc, actor, engine
    finally:
        app.dependency_overrides.clear()
        db_session.SessionLocal.configure(bind=old_bind)
        engine.dispose()


def test_list_search_filter_pagination_detail_and_permissions(context):
    client, kc, actor, _ = context
    response = client.get("/api/v1/admin/users", params={"page": 1, "page_size": 1})
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 2
    assert len(response.json()["items"]) == 1
    result = client.get("/api/v1/admin/users", params={"role": "user", "search": "user"})
    assert result.status_code == 200
    assert [item["id"] for item in result.json()["items"]] == [USER_ID]
    assert client.get(f"/api/v1/admin/users/{USER_ID}").json()["last_login_at"] is None
    actor.roles = {"manager"}
    assert client.get("/api/v1/admin/users").status_code == 403
    assert client.post(f"/api/v1/admin/users/{USER_ID}/block", json={"blocked": True}).status_code == 403
    actor.roles = {"user"}
    assert client.get("/api/v1/admin/users").status_code == 403
    actor.roles = {"admin"}
    kc.roles[ADMIN_ID] = {"user"}
    assert client.get("/api/v1/admin/users").status_code == 403


def test_manager_assigns_only_own_universities_without_admin_actions(context):
    client, kc, actor, engine = context
    with Session(engine) as db:
        own = University(name="Manager own")
        foreign = University(name="Manager foreign")
        db.add_all([own, foreign])
        db.commit()
        own_id, foreign_id = str(own.id), str(foreign.id)
    kc.records[MANAGER_ID] = {
        "id": MANAGER_ID, "username": "manager", "email": "manager@example.test",
        "enabled": True, "attributes": {"university_ids": [own_id]},
    }
    kc.roles[MANAGER_ID] = {"manager"}
    kc.records[USER_ID]["attributes"] = {"university_ids": [own_id, foreign_id]}
    for user_id, name, ids in (
        (FOREIGN_USER_ID, "foreign", [foreign_id]),
        (EMPTY_USER_ID, "unassigned", []),
    ):
        kc.records[user_id] = {
            "id": user_id, "username": name, "email": f"{name}@example.test",
            "enabled": True, "attributes": {"university_ids": ids},
        }
        kc.roles[user_id] = {"user"}
    actor.id, actor.roles, actor.university_ids = MANAGER_ID, {"manager"}, (foreign_id,)

    listed = client.get("/api/v1/admin/users")
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 2
    assert {item["id"] for item in listed.json()["items"]} == {USER_ID, EMPTY_USER_ID}
    assert client.get(f"/api/v1/admin/users/{USER_ID}").json()["scope"]["university_ids"] == [own_id]
    assert client.get(f"/api/v1/admin/users/{FOREIGN_USER_ID}").status_code == 404
    assert client.get(f"/api/v1/admin/users/{ADMIN_ID}").status_code == 404

    own_scope = {"kind": "universities", "university_ids": [own_id]}
    assert client.patch(f"/api/v1/admin/users/{FOREIGN_USER_ID}", json={
        "role": "user", "scope": own_scope,
    }).status_code == 404
    assert client.patch(f"/api/v1/admin/users/{USER_ID}", json={
        "role": "manager", "scope": own_scope,
    }).status_code == 403
    assert client.patch(f"/api/v1/admin/users/{USER_ID}", json={
        "role": "user", "scope": {"kind": "universities", "university_ids": [foreign_id]},
    }).status_code == 403
    assert client.post(f"/api/v1/admin/users/{USER_ID}/block", json={"blocked": True}).status_code == 403
    assert client.post(f"/api/v1/admin/users/{USER_ID}/password-reset").status_code == 403
    assert client.post("/api/v1/admin/users/invite", json={}).status_code == 403
    assert kc.roles[USER_ID] == {"user"}

    removed = client.patch(f"/api/v1/admin/users/{USER_ID}", json={
        "role": "user", "scope": {"kind": "universities", "university_ids": []},
    })
    assert removed.status_code == 200, removed.text
    assert removed.json()["scope"]["university_ids"] == []
    assert kc.records[USER_ID]["attributes"]["university_ids"] == [foreign_id]
    assert client.get(f"/api/v1/admin/users/{USER_ID}").status_code == 404
    assigned = client.patch(f"/api/v1/admin/users/{EMPTY_USER_ID}", json={
        "role": "user", "scope": own_scope,
    })
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["scope"]["university_ids"] == [own_id]
    assert kc.records[EMPTY_USER_ID]["attributes"]["university_ids"] == [own_id]
    assert kc.roles[EMPTY_USER_ID] == {"user"}

    kc.records[MANAGER_ID]["attributes"] = {"university_ids": []}
    assert client.get("/api/v1/admin/users").json()["items"] == []
    assert client.patch(f"/api/v1/admin/users/{EMPTY_USER_ID}", json={
        "role": "user", "scope": own_scope,
    }).status_code == 403
    kc.records[MANAGER_ID]["enabled"] = False
    assert client.get("/api/v1/admin/users").status_code == 403


def test_role_and_scope_update_restricts_catalog_api(context):
    client, kc, actor, engine = context
    with Session(engine) as db:
        university_a = University(name="A")
        university_b = University(name="B")
        db.add_all([university_a, university_b])
        db.commit()
        a, b = str(university_a.id), str(university_b.id)
    body = {"role": "manager", "scope": {"kind": "universities", "university_ids": [a]}}
    response = client.patch(f"/api/v1/admin/users/{USER_ID}", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "manager"
    assert response.json()["scope"]["university_ids"] == [a]
    assert kc.roles[USER_ID] == {"manager"}
    assert kc.records[USER_ID]["email"] == "user@example.test"
    assert kc.records[USER_ID]["firstName"] == "Тест"
    assert USER_ID in kc.logged_out
    with Session(engine) as db:
        assert db.scalars(select(AuditEvent).where(AuditEvent.action == "ADMIN_CONFIG")).all()

    # Simulated fresh login token with the Keycloak attribute claim.
    from app.main import app
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=USER_ID, roles={"manager"}, university_ids=(a,)
    )
    result = client.get("/api/v1/universities?page=1&page_size=100")
    assert result.status_code == 200, result.text
    assert [item["id"] for item in result.json()["items"]] == [a]
    assert b not in str(result.json())


def test_self_and_last_admin_protections(context):
    client, kc, actor, engine = context
    downgrade = {"role": "user", "scope": {"kind": "universities", "university_ids": []}}
    assert client.patch(f"/api/v1/admin/users/{ADMIN_ID}", json=downgrade).status_code == 403
    assert client.post(f"/api/v1/admin/users/{ADMIN_ID}/block", json={"blocked": True}).status_code == 403
    from app.modules.admin_users.service import _last_admin_guard
    from app.modules.admin_users.service import set_blocked
    from app.core.errors import ConflictError
    with Session(engine) as db:
        with pytest.raises(ConflictError):
            _last_admin_guard(db, kc, kc.user(ADMIN_ID), "admin")
        with pytest.raises(ConflictError):
            set_blocked(db, kc, CurrentUser(id=SECOND_ADMIN_ID, roles={"admin"}), ADMIN_ID, True)
    assert kc.records[ADMIN_ID]["enabled"] is True


def test_scope_validation_rejects_unknown_university_and_nonadmin_all(context):
    client, kc, _, _ = context
    unknown = "00000000-0000-4000-8000-000000000099"
    response = client.patch(f"/api/v1/admin/users/{USER_ID}", json={
        "role": "user", "scope": {"kind": "universities", "university_ids": [unknown]},
    })
    assert response.status_code == 422
    assert kc.records[USER_ID]["attributes"] == {}
    response = client.patch(f"/api/v1/admin/users/{USER_ID}", json={
        "role": "manager", "scope": {"kind": "all", "university_ids": []},
    })
    assert response.status_code == 422


def test_block_unblock_invite_duplicate_and_reset(context):
    client, kc, _, _ = context
    blocked = client.post(f"/api/v1/admin/users/{USER_ID}/block", json={"blocked": True})
    assert blocked.status_code == 200 and blocked.json()["status"] == "blocked"
    assert kc.records[USER_ID]["enabled"] is False
    assert kc.records[USER_ID]["email"] == "user@example.test"
    assert USER_ID in kc.logged_out
    unblocked = client.post(f"/api/v1/admin/users/{USER_ID}/block", json={"blocked": False})
    assert unblocked.status_code == 200 and unblocked.json()["status"] == "active"

    invite = {"name": "Новый Пользователь", "username": "new.user", "email": "new@example.test",
              "role": "user", "scope": {"kind": "universities", "university_ids": []}}
    created = client.post("/api/v1/admin/users/invite", json=invite)
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "email_sent"
    assert client.post("/api/v1/admin/users/invite", json=invite).status_code == 409
    uid = created.json()["user"]["id"]
    assert client.post(f"/api/v1/admin/users/{uid}/password-reset").json() == {"status": "requested"}
    kc.fail_email = True
    assert client.post(f"/api/v1/admin/users/{uid}/password-reset").status_code == 503
    invite["username"] = "another.user"
    invite["email"] = "another@example.test"
    unavailable = client.post("/api/v1/admin/users/invite", json=invite)
    assert unavailable.status_code == 201
    assert unavailable.json()["status"] == "invite_email_unavailable"


def test_provider_role_failure_compensates_scope_and_role(context):
    client, kc, _, engine = context
    with Session(engine) as db:
        university = University(name="Scope candidate")
        db.add(university)
        db.commit()
        scope_id = str(university.id)
    kc.fail_role_remove = True
    response = client.patch(f"/api/v1/admin/users/{USER_ID}", json={
        "role": "manager", "scope": {"kind": "universities", "university_ids": [scope_id]},
    })
    assert response.status_code >= 500
    assert kc.roles[USER_ID] == {"user"}
    assert kc.records[USER_ID]["attributes"] == {}


def test_keycloak_discarded_scope_is_not_reported_as_success(context):
    client, kc, _, engine = context
    with Session(engine) as db:
        university = University(name="Discarded scope")
        db.add(university)
        db.commit()
        scope_id = str(university.id)
    kc.ignore_attributes = True
    response = client.patch(f"/api/v1/admin/users/{USER_ID}", json={
        "role": "user", "scope": {"kind": "universities", "university_ids": [scope_id]},
    })
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "EXTERNAL_SYNC_FAILED"
    assert kc.records[USER_ID]["attributes"] == {}
    with Session(engine) as db:
        assert not db.scalars(select(AuditEvent).where(AuditEvent.action == "ADMIN_CONFIG")).all()


def test_keycloak_admin_errors_are_normalized(monkeypatch):
    import httpx
    from app.core.errors import BusinessException, ConflictError
    from app.modules.admin_users.keycloak_client import KeycloakAdminClient
    from app.schemas.errors import ErrorCode

    kc = KeycloakAdminClient()
    monkeypatch.setattr(kc, "_access_token", lambda: "test-token")
    monkeypatch.setattr(httpx, "request", lambda *args, **kwargs: httpx.Response(
        409, json={"errorMessage": "raw private provider detail"}, request=httpx.Request("GET", "http://keycloak.test")
    ))
    with pytest.raises(ConflictError) as conflict:
        kc.user(USER_ID)
    assert "raw private" not in str(conflict.value)

    monkeypatch.setattr(httpx, "request", lambda *args, **kwargs: httpx.Response(
        503, json={"errorMessage": "raw private provider detail"}, request=httpx.Request("GET", "http://keycloak.test")
    ))
    with pytest.raises(BusinessException) as unavailable:
        kc.user(USER_ID)
    assert unavailable.value.code == ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE
    assert "raw private" not in str(unavailable.value)
