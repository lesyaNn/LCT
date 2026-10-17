"""P0-1 guard: one schema universe + deferred modules stay unmounted.

Pins the resolution of the "two schema universes" blocker:
* canonical ``Base.metadata`` contains exactly the SQL-managed tables
  (P1 tables + B1 workflow tables from 000011-000014 + 1 P4 report job
  table ``report_jobs`` from 000018 + ``report_templates`` from 000032);
* pre-UUID / stub models live on ``DeferredBase`` metadata only;
* deferred routers are importable but NOT mounted in the production app;
* ``AuditEvent.user_id`` accepts Keycloak ``sub``; entity identity is UUID (000021).

The deferred-module table (reasons + reactivation checklist) lives in
``docs/DEFERRED_MODULES.md``; this test pins its enforcement side.

Pure-unit: no database, no Keycloak.
"""

import app.models  # noqa: F401  (register canon metadata)
from app.db.base import Base
from app.db.deferred import DeferredBase
from app.main import app

CANON_TABLES = frozenset(
    {
        "universities",
        "it_directions",
        "it_programs",
        "vendors",
        "it_products",
        "product_directions",
        "vendor_contacts",
        "contracts",
        "licenses",
        "responsibles",
        "university_responsibles",
        "university_programs",
        "university_products",
        "meetings",
        "meeting_documents",
        "documents",
        "interaction_notes",
        "audit_events",
        "workflow_templates",
        "workflow_stages",
        "workflow_instances",
        "workflow_stage_transitions",
        "workflow_comments",
        "workflow_attachments",
        "workflow_tasks",
        "instance_stages",
        "report_jobs",
        "report_templates",
        "audit_outbox",
        "external_applications",
        "external_sync_states",
        "notifications",
        "assistant_conversations",
        "assistant_turns",
        "teachers",
        "teacher_programs",
        "teacher_certificates",
        "teacher_qualifications",
        "program_education_stats",
    }
)

DEFERRED_TABLES = frozenset(
    {
        "workflow_statuses",
        "workflow_transitions",
        "workflows",
        "tasks",
        "files",
        "users",
    }
)

# Router prefixes (without the /api/v1 mount prefix) that must stay
# unmounted until the reactivation checklist in docs/DEFERRED_MODULES.md is done.
# NOTE (P2-08-03): "/health-score" стал production (ranking) и убран отсюда;
# NOTE (P4-06-01): "/reports" стал production (canonical async reports:
# POST queued job + status + download, migration 000018) и убран отсюда;
# legacy demo stub app/modules/reporting (POST /export over an in-memory
# queue) при этом остаётся незамаунченным (см. test_legacy_reporting_stub).
DEFERRED_API_PREFIXES = (
    "/dashboard", "/documents", "/users",
    "/workflows", "/tasks",
)


def _mounted_api_paths() -> list[str]:
    return sorted(path for path in app.openapi()["paths"] if path.startswith("/api/"))


def test_canon_metadata_is_exactly_the_sql_managed_set():
    assert frozenset(Base.metadata.tables) == CANON_TABLES


def test_deferred_tables_not_on_canon_metadata():
    assert not (DEFERRED_TABLES & frozenset(Base.metadata.tables))


def test_deferred_models_isolated_on_deferred_base():
    import app.modules.documents.models as documents_models
    import app.modules.identity.models as identity_models
    import app.modules.workflow.models as workflow_models

    for mod in (documents_models, identity_models, workflow_models):
        for name in (
            "FileMeta",
            "User",
            "Workflow",
            "WorkflowStatus",
            "WorkflowTransition",
            "Task",
        ):
            cls = getattr(mod, name, None)
            if cls is not None:
                assert issubclass(cls, DeferredBase), name
    assert DEFERRED_TABLES <= frozenset(DeferredBase.metadata.tables)


def test_mounted_routers_are_only_the_production_contract():
    allowed = (
        "/api/v1/service-api",  # Read-only catalog of mounted methods.
        "/api/v1/openapi.json",  # Authenticated alias through the frontend API proxy.
        "/api/v1/auth",
        "/api/v1/notifications",
        "/api/v1/assistant",
        "/api/v1/search",
        "/api/v1/teachers",
        "/api/v1/health-score",
        "/api/v1/admin/users",  # Keycloak-backed Admin API; legacy /users stays deferred.
        "/api/v1/import",
        "/api/v1/integrations",
        "/api/v1/catalog",
        "/api/v1/universities",
        "/api/v1/meetings",
        "/api/v1/directions",
        "/api/v1/programs",
        "/api/v1/products",
        "/api/v1/vendors",
        "/api/v1/responsibles",
        "/api/v1/contracts",  # Catalogs CRUD: contracts + licences (hard delete, 409 on reference).
        "/api/v1/licenses",
        "/api/v1/workflow",
        "/api/v1/analytics",
        "/api/v1/reports",
        "/api/v1/audit/events",
        "/api/v1/audit/filter-options",
    )
    paths = _mounted_api_paths()
    assert all(path.startswith(allowed) for path in paths), paths


def test_deferred_prefixes_absent_from_openapi_paths():
    """Deferred forward scaffolding must not leak into the prod contract.

    Module list mirrors ``docs/DEFERRED_MODULES.md``: universities-CRUD,
    programs, workflow, documents,
    dashboard, reporting. P5 mounted audit events and Stage 11
    mounts the canonical /integrations API; old mock fallback is gone.
    """
    paths = _mounted_api_paths()
    for prefix in DEFERRED_API_PREFIXES:
        assert not [p for p in paths if p.startswith(f"/api/v1{prefix}")], prefix


def test_legacy_reporting_stub_stays_unmounted():
    """Legacy demo stub (``POST /export`` over an in-memory queue) is NOT
    the production report path and must never be mounted alongside the
    canonical P4-06-01 ``/api/v1/reports`` contract (single creation path).
    """
    from app.modules.reporting.router import router as legacy_router

    # NOTE: route.path already carries the router prefix on some FastAPI
    # versions (and prefix+path on others) — assert on suffixes.
    legacy_paths = {getattr(route, "path", "") for route in legacy_router.routes}
    assert any(p.endswith("/reports/export") or p == "/export" for p in legacy_paths)
    assert any(p.endswith("/reports/jobs/{job_id}") for p in legacy_paths)
    mounted = _mounted_api_paths()
    assert not [p for p in mounted if p.endswith("/export")], mounted
    assert not [p for p in mounted if "/jobs/" in p and "reports" in p], mounted


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
            raise AssertionError("AuditService must not commit")

        def refresh(self, ev):
            pass

    import uuid

    ev = AuditService(_DB()).log("sub-abc", "university", uuid.uuid4(), "update")  # type: ignore[arg-type]
    assert isinstance(ev, AuditEvent)
    assert isinstance(seen["ev"].user_id, str)
    assert isinstance(seen["ev"].entity_id, uuid.UUID)
