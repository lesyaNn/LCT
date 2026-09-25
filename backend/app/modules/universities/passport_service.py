"""P1-04 passport aggregations (service layer, no SQL in routers).

M1: this module is the stable public facade — SQL loading lives in
``passport_loading``, DTO assembly in ``passport_blocks``. All public names
are re-exported here so existing imports (routers, tests, scripts) keep
working unchanged.
"""

from app.modules.universities.passport_blocks import (
    PassportInclude,
    parse_include,
    get_documents,
    get_health_score_for_passport,
    get_meetings,
    get_passport,
    get_products_licenses_contracts,
    get_programs,
    get_programs_page,
    get_recent_audit,
    get_responsibles,
    get_students_summary,
    get_teachers,
    get_teachers_page,
    get_timeline,
    get_workflow_summary,
    get_workflow_transitions,
)
from app.modules.universities.passport_loading import (
    AUDIT_LIMIT,
    DOCUMENTS_LIMIT,
    MEETINGS_LIMIT,
    TIMELINE_LIMIT,
    PassportLoadContext,
)

__all__ = [
    "AUDIT_LIMIT",
    "DOCUMENTS_LIMIT",
    "MEETINGS_LIMIT",
    "TIMELINE_LIMIT",
    "PassportInclude",
    "PassportLoadContext",
    "parse_include",
    "get_passport",
    "get_programs",
    "get_programs_page",
    "get_teachers",
    "get_teachers_page",
    "get_students_summary",
    "get_products_licenses_contracts",
    "get_documents",
    "get_meetings",
    "get_responsibles",
    "get_timeline",
    "get_workflow_summary",
    "get_workflow_transitions",
    "get_health_score_for_passport",
    "get_recent_audit",
]
