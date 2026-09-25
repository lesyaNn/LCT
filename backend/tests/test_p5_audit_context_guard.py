"""H3: fail-closed guard — every mounted mutating route needs audit context.

Pure-unit (no database): walks all routers mounted in ``app.api.router.v1``
and asserts that POST/PUT/PATCH/DELETE operations resolve ``get_audit_db``
(not bare ``get_db``), so mutations never silently skip the audit trail.
Read-only GET routes are exempt.
"""

from fastapi.routing import APIRoute

from app.modules.analytics.reports_router import router as reports_router
from app.modules.analytics.router import router as analytics_router
from app.modules.audit.router import router as audit_router
from app.modules.audit.service import get_audit_db
from app.modules.auth.router import router as auth_router
from app.modules.catalog.router import router as catalog_router
from app.modules.health_score.health_router import router as health_router
from app.modules.health_score.ranking_router import router as ranking_router
from app.modules.imports.router import router as imports_router
from app.modules.meetings.router import router as meetings_router
from app.modules.students.router import router as students_router
from app.modules.teachers.passport_router import router as teacher_passport_router
from app.modules.universities.passport_router import router as passport_router
from app.modules.workflow_attachments.router import router as workflow_attachments_router
from app.modules.workflow_instances.router import router as workflow_instances_router
from app.modules.workflow_templates.router import router as workflow_templates_router
from app.modules.workflow_transitions.router import router as workflow_transitions_router

#: All routers mounted in ``app.api.router.v1`` (same list, kept explicit so
#: a newly mounted router must be added here too — otherwise it is unaudited).
MOUNTED_ROUTERS = (
    auth_router,
    imports_router,
    health_router,
    ranking_router,
    passport_router,
    teacher_passport_router,
    meetings_router,
    students_router,
    catalog_router,
    workflow_templates_router,
    workflow_instances_router,
    workflow_transitions_router,
    workflow_attachments_router,
    reports_router,
    audit_router,
    analytics_router,
)


def _dependency_names(dependant, out: set[str]) -> None:
    for sub in getattr(dependant, "dependencies", []):
        if sub.call is not None:
            out.add(getattr(sub.call, "__name__", repr(sub.call)))
        _dependency_names(sub, out)


def _iter_mounted_routes():
    seen: set[int] = set()
    for mounted in MOUNTED_ROUTERS:
        for route in mounted.routes:
            if not isinstance(route, APIRoute):
                continue
            if id(route) in seen:
                continue
            seen.add(id(route))
            yield route


def test_mutating_routes_use_audit_db():
    offenders = []
    for route in _iter_mounted_routes():
        methods = set(route.methods or {}) - {"OPTIONS", "HEAD"}
        if not methods & {"POST", "PUT", "PATCH", "DELETE"}:
            continue
        names: set[str] = set()
        _dependency_names(route.dependant, names)
        if get_audit_db.__name__ not in names:
            offenders.append(f"{sorted(methods)} {route.path} -> {sorted(names)}")
    assert not offenders, (
        "Mutating routes without get_audit_db (silent audit no-op, H3):\n"
        + "\n".join(offenders)
    )


def test_attachments_upload_delete_audited():
    names_by_route = {}
    for route in _iter_mounted_routes():
        if "attachments" not in route.path:
            continue
        names: set[str] = set()
        _dependency_names(route.dependant, names)
        names_by_route[(tuple(sorted(route.methods)), route.path)] = names
    mutating = {
        key: names for key, names in names_by_route.items()
        if set(key[0]) & {"POST", "DELETE"}
    }
    assert mutating, "attachment mutating routes not found"
    for key, names in mutating.items():
        assert get_audit_db.__name__ in names, f"{key} misses get_audit_db"
