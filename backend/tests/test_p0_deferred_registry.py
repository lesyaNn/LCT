"""P0-1 guard: one schema universe + deferred modules stay unmounted.

Pins the resolution of the "two schema universes" blocker:
* canonical ``Base.metadata`` contains exactly the 29 SQL-managed tables;
* pre-UUID / stub models live on ``DeferredBase`` metadata only;
* deferred routers are importable but NOT mounted in the production app;
* ``AuditEvent.user_id/entity_id`` accept Keycloak ``sub`` (TEXT, 000010).

The deferred-module table (reasons + reactivation checklist) lives in
``docs/AUDIT.md`` (§0); this test pins its enforcement side.

Pure-unit: no database, no Keycloak.
"""

import app.models  # noqa: F401  (register canon metadata)
from app.api.router import v1
from app.db.base import Base
from app.db.deferred import DeferredBase
from app.main import app

CANON_TABLES = frozenset({
    "universities", "it_directions", "it_programs", "vendors", "it_products",
    "contracts", "licenses", "responsibles", "university_responsibles",
    "teachers", "teacher_qualifications", "teacher_certificates",
    "teacher_programs", "students", "university_programs",
    "university_products", "meetings", "meeting_documents", "documents",
    "interaction_notes", "audit_events",
    "workflow_templates", "workflow_stages", "workflow_instances",
    "instance_stages", "transitions", "comments", "tasks", "attachments",
})

DEFERRED_TABLES = frozenset({
    "workflow_statuses", "workflow_transitions", "workflows", "tasks",
    "files", "health_score_history", "users",
})

# Router prefixes (without the /api/v1 mount prefix) that must stay
# unmounted until the reactivation checklist in docs/AUDIT.md (§0) is done.
DEFERRED_API_PREFIXES = (
    "/audit", "/dashboard", "/documents", "/health-score", "/users",
    "/integrations", "/notifications", "/reports", "/workflows", "/tasks",
)


def _mounted_api_paths() -> list[str]:
    paths: list[str] = []

    def _walk(routes, prefix: str = "") -> None:
        for route in routes:
            path = getattr(route, "path", None)
            if path:
                paths.append(f"{prefix}{path}")
                continue
            nested = getattr(route, "routes", None)
            original = getattr(route, "original_router", None)
            if original is not None:
                # FastAPI >=0.120 nests included routers (_IncludedRouter):
                # descend via original_router, accumulating its prefix.
                _walk(original.routes, f"{prefix}{original.prefix or ''}")
            elif nested:
                mount = getattr(route, "prefix", "") or ""
                _walk(nested, f"{prefix}{mount}")

    _walk(app.routes)
    return sorted(p for p in paths if p.startswith("/api/"))


def test_canon_metadata_is_exactly_the_sql_managed_set():
    assert frozenset(Base.metadata.tables) == CANON_TABLES


def test_deferred_tables_not_on_canon_metadata():
    # Canonical UUID tasks and legacy integer tasks share only the SQL name.
    assert not ((DEFERRED_TABLES - {"tasks"}) & frozenset(Base.metadata.tables))
    from app.models.workflow import WorkflowTask
    from app.modules.workflow.models import Task

    assert WorkflowTask.__table__ is not Task.__table__
    assert Task.__table__.metadata is DeferredBase.metadata


def test_deferred_models_isolated_on_deferred_base():
    import app.modules.documents.models as documents_models
    import app.modules.health_score.models as health_score_models
    import app.modules.identity.models as identity_models
    import app.modules.workflow.models as workflow_models

    for mod in (documents_models, health_score_models,
                identity_models, workflow_models):
        for name in ("FileMeta", "HealthScoreHistory", "User",
                     "Workflow", "WorkflowStatus", "WorkflowTransition", "Task"):
            cls = getattr(mod, name, None)
            if cls is not None:
                assert issubclass(cls, DeferredBase), name
    assert DEFERRED_TABLES <= frozenset(DeferredBase.metadata.tables)


def test_mounted_routers_are_only_the_production_contract():
    allowed = (
        "/api/v1/auth", "/api/v1/import", "/api/v1/catalog",
        "/api/v1/universities", "/api/v1/directions", "/api/v1/programs",
        "/api/v1/products", "/api/v1/vendors", "/api/v1/responsibles",
        "/api/v1/teachers", "/api/v1/workflow",
    )
    paths = _mounted_api_paths()
    assert all(path.startswith(allowed) for path in paths), paths


def test_deferred_prefixes_absent_from_openapi_paths():
    """Deferred forward scaffolding must not leak into the prod contract.

    Module list mirrors ``docs/AUDIT.md`` (§0): universities-CRUD,
    teachers-CRUD, programs, workflow, documents, health_score, identity,
    audit, dashboard, reporting, integrations, notifications.
    """
    paths = _mounted_api_paths()
    for prefix in DEFERRED_API_PREFIXES:
        assert not [p for p in paths if p.startswith(f"/api/v1{prefix}")], prefix


def test_universities_mount_is_passport_or_catalog_crud():
    paths = _mounted_api_paths()
    uni = [p for p in paths if p.startswith("/api/v1/universities")]
    assert uni, "passport router must stay mounted"
    assert any("/passport" in p for p in uni), uni


def test_audit_identity_columns_accept_keycloak_sub():
    from sqlalchemy import Integer

    from app.modules.audit.models import AuditEvent

    for attr in ("user_id", "entity_id"):
        col_type = AuditEvent.__table__.c[attr].type
        assert not isinstance(col_type, Integer), attr


def test_audit_service_coerces_identity_to_str():
    from app.modules.audit.service import AuditService
    from app.modules.audit.models import AuditEvent

    seen: dict = {}

    class _DB:
        def add(self, ev):
            seen["ev"] = ev

        def commit(self):
            pass

        def refresh(self, ev):
            pass

    import uuid

    ev = AuditService(_DB()).log("sub-abc", "university", uuid.uuid4(), "update")  # type: ignore[arg-type]
    assert isinstance(ev, AuditEvent)
    assert isinstance(seen["ev"].user_id, str)
    assert isinstance(seen["ev"].entity_id, str)

