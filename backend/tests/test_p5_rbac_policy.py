"""P5 public-role and data-scope contract, independent of a test database."""

import uuid

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.core.errors import SecurityError, register_error_handlers
from app.core.logging import request_log_middleware
from app.core.permissions import (
    ADMIN_PERMISSIONS,
    CURATOR_PERMISSIONS,
    MANAGER_PERMISSIONS,
    PUBLIC_ROLE_NAMES,
    USER_PERMISSIONS,
    require_permission,
    user_permissions,
)
from app.core.policies import (
    ScopeKind,
    apply_university_scope,
    ensure_university_access,
    ensure_university_visible,
    get_data_scope,
)
from app.core.security import CurrentUser, get_current_user
from app.models.catalog import University
from app.schemas.errors import ErrorCode, ErrorResponse

A = uuid.uuid4()
B = uuid.uuid4()


def actor(*roles, ids=None):
    return CurrentUser(id="actor", roles=set(roles), university_ids=ids)


def test_registry_and_curator_compatibility():
    assert PUBLIC_ROLE_NAMES == {"user", "manager", "admin"}
    assert USER_PERMISSIONS <= MANAGER_PERMISSIONS <= ADMIN_PERMISSIONS
    assert user_permissions(actor("user")) == USER_PERMISSIONS
    assert user_permissions(actor("manager")) == MANAGER_PERMISSIONS
    assert user_permissions(actor("admin")) == ADMIN_PERMISSIONS
    assert user_permissions(actor("curator")) == CURATOR_PERMISSIONS
    assert "audit.read" not in CURATOR_PERMISSIONS
    assert "university_responsible.manage" not in CURATOR_PERMISSIONS
    assert "admin.users" not in CURATOR_PERMISSIONS
    assert "audit.read" not in USER_PERMISSIONS
    assert {"workflow.task.read", "workflow.task.update", "reports.create"} <= USER_PERMISSIONS
    assert {"university_responsible.manage", "analytics.extended", "audit.read"} <= MANAGER_PERMISSIONS
    assert {"workflow_template.manage", "admin.users", "admin.settings"} <= ADMIN_PERMISSIONS
    assert "workflow_template.manage" not in MANAGER_PERMISSIONS


@pytest.mark.parametrize(
    ("roles", "ids", "kind", "visible"),
    [
        (("user",), (str(A),), ScopeKind.OWN, {A}),
        (("user",), (), ScopeKind.OWN, set()),
        (("user",), None, ScopeKind.OWN, set()),
        (("manager",), (str(B),), ScopeKind.GROUP, {B}),
        (("manager",), (), ScopeKind.GROUP, set()),
        (("manager",), None, ScopeKind.GROUP, set()),
        (("admin",), None, ScopeKind.ALL, set()),
        (("admin", "user"), (str(A),), ScopeKind.ALL, set()),
        (("manager", "user"), (str(B),), ScopeKind.GROUP, {B}),
        (("curator",), (str(A),), ScopeKind.DENY, set()),
        (("curator",), None, ScopeKind.DENY, set()),
        (("curator", "user"), (str(A),), ScopeKind.OWN, {A}),
        (("unknown",), (str(A),), ScopeKind.DENY, set()),
    ],
)
def test_scope_precedence_and_missing_claim(roles, ids, kind, visible):
    scope = get_data_scope(actor(*roles, ids=ids))
    assert scope.kind is kind
    assert scope.university_ids == visible


def test_object_guard_is_generic_and_fail_closed():
    ensure_university_access(A, actor("user", ids=(str(A),)))
    ensure_university_access(B, actor("admin"))
    for user in (actor("user", ids=(str(A),)), actor("manager"), actor("unknown", ids=(str(B),))):
        with pytest.raises(SecurityError) as caught:
            ensure_university_access(B, user)
        assert caught.value.code == ErrorCode.FORBIDDEN


def test_detail_guard_conceals_foreign_objects():
    ensure_university_visible(A, actor("user", ids=(str(A),)))
    with pytest.raises(Exception) as caught:
        ensure_university_visible(B, actor("user", ids=(str(A),)))
    assert caught.value.code == ErrorCode.NOT_FOUND


def test_sql_scope_precedes_count_and_filter_intersection():
    user = actor("user", ids=(str(B),))
    statement = apply_university_scope(
        select(University.id).where(University.id == A), University.id, user
    )
    sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert str(A) in sql and str(B) in sql and " AND " in sql
    count = apply_university_scope(select(University.id), University.id, actor("manager"))
    assert "false" in str(count.compile(dialect=postgresql.dialect())).lower()
    admin = apply_university_scope(select(University.id), University.id, actor("admin"))
    assert admin.whereclause is None


def test_permission_denial_has_frozen_response():
    api = FastAPI()
    register_error_handlers(api)
    api.middleware("http")(request_log_middleware)

    @api.get("/audit")
    def audit(_user: CurrentUser = Depends(require_permission("audit.read"))):
        return {"ok": True}

    api.dependency_overrides[get_current_user] = lambda: actor("user")
    response = TestClient(api).get("/audit")
    assert response.status_code == 403
    body = ErrorResponse.model_validate(response.json())
    assert body.error.code == ErrorCode.FORBIDDEN
    assert body.error.details == {}
    assert response.headers["X-Request-ID"] == str(body.error.request_id)
    assert "audit" not in response.text.lower()
