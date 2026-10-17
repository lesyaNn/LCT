"""Admin Users integration tests with an in-memory Keycloak Admin API seam."""

import os
import uuid
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.config import settings
from app.models.catalog import Responsible, University
from app.models.notification import Notification
from app.models.notification_delivery import NotificationDelivery
from app.modules.admin_users.keycloak_client import get_keycloak_admin_client
from app.modules.audit.models import AuditEvent
from app.modules.notifications import email

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


@pytest.mark.parametrize("old_names,new_names,expected_names", [
    ([], ["Альфа"], ["Альфа"]),
    (["Альфа"], ["Альфа", "Бета"], ["Бета"]),
    (["Альфа"], ["Альфа"], []),
    (["Альфа", "Бета"], ["Альфа"], []),
    ([], ["Альфа", "Бета", "Гамма"], ["Альфа", "Бета", "Гамма"]),
])
def test_scope_assignment_notification_diff(context, monkeypatch, old_names, new_names,
                                            expected_names):
    client, kc, actor, engine = context
    monkeypatch.setattr(settings, "email_notifications_enabled", True)
    with Session(engine) as db:
        universities = {name: University(name=name) for name in ("Альфа", "Бета", "Гамма")}
        db.add_all(universities.values())
        db.commit()
        ids = {name: str(university.id) for name, university in universities.items()}
    kc.records[USER_ID]["attributes"] = {"university_ids": [ids[name] for name in old_names]}
    response = client.patch(f"/api/v1/admin/users/{USER_ID}", json={
        "role": "user", "scope": {"kind": "universities",
                                   "university_ids": [ids[name] for name in new_names]},
    })
    assert response.status_code == 200, response.text
    assert set(kc.records[USER_ID]["attributes"]["university_ids"]) == {
        ids[name] for name in new_names
    }
    with Session(engine) as db:
        rows = db.scalars(select(Notification)).all()
        assert len(rows) == bool(expected_names)
        assert db.scalar(select(func.count()).select_from(NotificationDelivery)) == int(bool(expected_names))
        if rows:
            row = rows[0]
            assert row.recipient_user_id == USER_ID != actor.id
            assert row.priority == "INFO" and row.type == "user_university_assigned"
            assert row.event_key.startswith("user-university-assigned:")
            audit = db.get(AuditEvent, uuid.UUID(row.event_key.removeprefix(
                "user-university-assigned:"
            )))
            assert audit.new_value["kind"] == "scope"
            assert all(name in row.message for name in expected_names)
            assert all(name not in row.message for name in set(universities) - set(expected_names))
            if len(expected_names) == 1:
                assert row.title == "Вам назначен новый ВУЗ"
                assert row.entity_type == "university"
                assert row.entity_id == ids[expected_names[0]]
                assert row.university_id == universities[expected_names[0]].id
                assert email.target_path(row) == f"/universities/{row.entity_id}"
            else:
                assert row.title == "Вам назначены новые ВУЗы"
                assert row.entity_type == "universities" and row.university_id is None
                assert email.target_path(row) == "/universities"
    if expected_names:
        assert client.get("/api/v1/notifications/unread-count").json() == {"count": 0}
        actor.id, actor.roles, actor.university_ids = USER_ID, {"user"}, tuple(
            ids[name] for name in new_names
        )
        assert client.get("/api/v1/notifications/unread-count").json() == {"count": 1}
        inbox = client.get("/api/v1/notifications")
        assert inbox.status_code == 200
        if len(expected_names) == 1:
            target = ids[expected_names[0]]
            assert inbox.json()["items"][0]["entity_type"] == "university"
            assert inbox.json()["items"][0]["entity_id"] == target
            assert client.get(f"/api/v1/universities/{target}").status_code == 200
        else:
            assert inbox.json()["items"][0]["entity_type"] == "universities"
            assert client.get("/api/v1/universities").status_code == 200


def test_scope_assignment_old_and_new_claims(context, monkeypatch):
    client, kc, actor, engine = context
    monkeypatch.setattr(settings, "email_notifications_enabled", True)
    with Session(engine) as db:
        university = University(name="Новый вуз")
        db.add(university)
        db.commit()
        university_id = str(university.id)
    response = client.patch(f"/api/v1/admin/users/{USER_ID}", json={
        "role": "user", "scope": {"kind": "universities", "university_ids": [university_id]},
    })
    assert response.status_code == 200, response.text
    assert USER_ID in kc.logged_out
    actor.id, actor.roles, actor.university_ids = USER_ID, {"user"}, ()
    assert client.get("/api/v1/notifications/unread-count").json() == {"count": 0}
    assert client.get(f"/api/v1/universities/{university_id}").status_code == 404
    actor.university_ids = (university_id,)
    assert client.get("/api/v1/notifications/unread-count").json() == {"count": 1}
    assert client.get(f"/api/v1/universities/{university_id}").status_code == 200


@pytest.mark.parametrize("keycloak_email", [None, "bad-address", "first,second@example.test",
                                               "user@example.test\r\nBcc:other@example.test"])
def test_scope_assignment_missing_or_invalid_email_is_in_app_only(
    context, monkeypatch, keycloak_email,
):
    client, kc, _, engine = context
    monkeypatch.setattr(settings, "email_notifications_enabled", True)
    kc.records[USER_ID]["email"] = keycloak_email
    with Session(engine) as db:
        university = University(name="Новый вуз")
        db.add(university)
        db.add(Responsible(full_name="Резервный контакт", email="responsible@example.test",
                           role="user", keycloak_sub=USER_ID))
        db.commit()
        university_id = str(university.id)
    response = client.patch(f"/api/v1/admin/users/{USER_ID}", json={
        "role": "user", "scope": {"kind": "universities", "university_ids": [university_id]},
    })
    assert response.status_code == 200, response.text
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == 1
        assert db.scalar(select(func.count()).select_from(Notification)) == 1
        assert db.scalar(select(func.count()).select_from(NotificationDelivery)) == 0


def test_scope_assignment_delivery_insert_failure_keeps_audit(context, monkeypatch):
    client, _, _, engine = context
    monkeypatch.setattr(settings, "email_notifications_enabled", True)
    with Session(engine) as db:
        university = University(name="Новый вуз")
        db.add(university)
        db.commit()
        university_id = str(university.id)
        db.execute(text("ALTER TABLE notification_deliveries "
                        "ADD CONSTRAINT test_reject_enqueue CHECK (false)"))
        db.commit()
    response = client.patch(f"/api/v1/admin/users/{USER_ID}", json={
        "role": "user", "scope": {"kind": "universities", "university_ids": [university_id]},
    })
    assert response.status_code == 200, response.text
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == 1
        assert db.scalar(select(func.count()).select_from(Notification)) == 1
        assert db.scalar(select(func.count()).select_from(NotificationDelivery)) == 0


def test_scope_assignment_idempotent_repeat_and_readd(context, monkeypatch):
    client, kc, _, engine = context
    monkeypatch.setattr(settings, "email_notifications_enabled", True)
    with Session(engine) as db:
        university = University(name="Альфа")
        db.add(university)
        db.commit()
        university_id = str(university.id)

    def save(ids):
        response = client.patch(f"/api/v1/admin/users/{USER_ID}", json={
            "role": "user", "scope": {"kind": "universities", "university_ids": ids},
        })
        assert response.status_code == 200, response.text

    save([university_id])
    save([university_id])
    with Session(engine) as db:
        first_key = db.scalar(select(Notification.event_key))
        assert db.scalar(select(func.count()).select_from(Notification)) == 1
        assert db.scalar(select(func.count()).select_from(NotificationDelivery)) == 1
    save([])
    save([university_id])
    with Session(engine) as db:
        rows = db.scalars(select(Notification)).all()
        assert len(rows) == 2
        assert db.scalar(select(func.count()).select_from(NotificationDelivery)) == 2
        assert {row.event_key for row in rows} == {first_key, rows[1].event_key}
        assert rows[1].event_key != first_key
    assert kc.records[USER_ID]["attributes"]["university_ids"] == [university_id]


def test_scope_assignment_email_delivery_uses_existing_worker(context, monkeypatch):
    client, kc, _, engine = context
    monkeypatch.setattr(settings, "email_notifications_enabled", True)
    with Session(engine) as db:
        university = University(name="Альфа")
        other = University(name="Бета")
        third = University(name="Гамма")
        db.add_all([university, other, third])
        db.add(Responsible(full_name="Получатель", email="responsible@example.test",
                           role="user", keycloak_sub=USER_ID))
        db.commit()
        university_id = str(university.id)
        other_ids = [str(other.id), str(third.id)]
    response = client.patch(f"/api/v1/admin/users/{USER_ID}", json={
        "role": "user", "scope": {"kind": "universities", "university_ids": [university_id]},
    })
    assert response.status_code == 200, response.text
    with Session(engine) as db:
        delivery = db.scalar(select(NotificationDelivery))
        assert delivery.recipient == "user@example.test"
        assert delivery.status == "pending"
        kc.records[USER_ID]["email"] = "changed@example.test"
        sent = []
        assert email.run_email_delivery_once(db, sender=lambda *args: sent.append(args))
        assert db.get(NotificationDelivery, delivery.id).status == "sent"
        assert len(sent) == 1
        assert sent[0][0] == "user@example.test"
        assert sent[0][1] == "Вам назначен новый ВУЗ"
        assert f"/universities/{university_id}" in sent[0][2]
    response = client.patch(f"/api/v1/admin/users/{USER_ID}", json={
        "role": "user", "scope": {"kind": "universities",
                                   "university_ids": [university_id, *other_ids]},
    })
    assert response.status_code == 200, response.text
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Notification)) == 2
        assert db.scalar(select(func.count()).select_from(NotificationDelivery)) == 2
        assert email.run_email_delivery_once(db, sender=lambda *args: sent.append(args))
        assert len(sent) == 2
        assert sent[1][0] == "changed@example.test"
        assert sent[1][1] == "Вам назначены новые ВУЗы"
        assert "/universities" in sent[1][2]


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
        assert db.scalar(select(func.count()).select_from(Notification)) == 0
        assert db.scalar(select(func.count()).select_from(NotificationDelivery)) == 0


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
