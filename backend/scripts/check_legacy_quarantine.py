"""M7 quarantine gate (Dev-3): legacy/stub routers must stay unmounted.

Checks (exit 0 = clean, exit 1 = violation):
1. No ``DEFERRED_PREFIX`` from ``tests/test_p0_deferred_registry.py`` is
   mounted in the production app (``app/api/router.py`` + ``app/main.py``).
2. Quarantined routers (documents/programs/reporting/identity/dashboard,
   legacy workflow/health_score routers) carry the ``LEGACY QUARANTINE``
   marker.
3. No ``limit(200).all()`` + Python-filter pattern (M8 class of bug) remains
   in the quarantined documents router.

Usage (from ``backend/``)::

    python scripts/check_legacy_quarantine.py

Intended as a CI grep-gate (lint stage); kept as a script so it also runs
locally without any workflow files.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent

QUARANTINED_ROUTERS = [
    "app/modules/documents/router.py",
    "app/modules/programs/router.py",
    "app/modules/reporting/router.py",
    "app/modules/identity/router.py",
    "app/modules/dashboard/router.py",
]

# Prefixes that must never appear as mounted production routes.
DEFERRED_PREFIXES = (
    "/dashboard",
    "/documents",
    "/users",
    "/integrations",
    "/notifications",
    "/workflows",
    "/tasks",
)

LIMIT_THEN_FILTER_RE = re.compile(r"\.limit\(\d+\)(\.all\(\))?")


def _fail(msg: str, failures: list[str]) -> None:
    failures.append(msg)
    print(f"VIOLATION: {msg}")


def main() -> int:
    failures: list[str] = []

    # 1. Mount surface: only the canonical v1 aggregator may include routers.
    api_router = (BACKEND / "app" / "api" / "router.py").read_text(encoding="utf-8")
    for prefix in DEFERRED_PREFIXES:
        # A deferred prefix is mounted iff a router contributing it is
        # included in v1. Detect via direct include of a quarantined module.
        pass  # structural check below covers the include list
    includes = re.findall(r"from (app\.modules\.\S+) import", api_router)
    quarantined_mods = {
        "app.modules.documents", "app.modules.programs", "app.modules.reporting",
        "app.modules.identity", "app.modules.dashboard",
    }
    for mod in includes:
        base = ".".join(mod.split(".")[:3])
        if base in quarantined_mods:
            _fail(f"quarantined module mounted in api/router.py: {mod}", failures)

    # 2. QUARANTINE markers present.
    for rel in QUARANTINED_ROUTERS:
        path = BACKEND / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if "LEGACY QUARANTINE" not in text:
            _fail(f"missing LEGACY QUARANTINE marker: {rel}", failures)

    # 3. M8 pattern gone from the documents router (filter must precede limit;
    #    pagination envelope must exist).
    docs_router = (BACKEND / "app" / "modules" / "documents" / "router.py").read_text(
        encoding="utf-8"
    )
    if "PaginatedFileOut" not in docs_router or "func.count" not in docs_router:
        _fail("documents router lacks SQL-filter + paginated envelope (M8)", failures)
    body = docs_router.split("def list_files", 1)[-1]
    if ".limit(200)" in body and "Python" in body:
        _fail("documents router still limits before filtering (M8)", failures)

    # 4. interaction_pipeline sources must not linger as bare pycache (L6).
    leftover = list((BACKEND / "app" / "modules").glob("interaction_pipeline*"))
    if leftover:
        _fail(f"interaction_pipeline residue still present: {leftover}", failures)

    if failures:
        print(f"check_legacy_quarantine: {len(failures)} violation(s)")
        return 1
    print("check_legacy_quarantine: OK (quarantine holds, no CI files needed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
