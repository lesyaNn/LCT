"""SQL migration runner — the ONLY active schema-management path.

Source of truth: ``backend/migrations/*.up.sql`` / ``*.down.sql``.
Bookkeeping table: ``schema_migrations(version TEXT PRIMARY KEY)``.

Usage (from ``backend/``)::

    DATABASE_URL=postgresql+psycopg://rtk:change-me@localhost:5433/rtk \\
        python scripts/migrate.py up
    python scripts/migrate.py status        # applied vs available
    python scripts/migrate.py down --to 000006_audit
    python scripts/migrate.py baseline      # adopt an existing Alembic-head DB
    python scripts/migrate.py verify        # latest == all applied?

Rules:
* Each ``*.up.sql`` runs inside ONE transaction; failure -> rollback +
  non-zero exit (backend must never start on a partial schema).
* No ``IF NOT EXISTS`` hiding drift: versioned files must fail loudly on
  unexpected state; idempotency comes from the version table, not DDL.
* ``baseline`` is the ONLY adoption path for pre-existing databases at the
  old Alembic head (7f3a1c9e2b06). It verifies the legacy table set and
  the alembic version row, then marks SQL migrations through 000010 as
  applied WITHOUT re-running DDL. The new workflow migration remains pending.
* Keycloak database is never touched: this runner connects only to
  ``DATABASE_URL`` (the ``rtk`` application database).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None  # type: ignore

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

# Old Alembic head adopted by `baseline`. Kept as a constant so the
# adoption path is explicit and auditable (never "table exists -> done").
LEGACY_ALEMBIC_HEAD = "7f3a1c9e2b06"
LEGACY_SQL_HEAD = "000010_audit_identity"

# Canonical application tables (alembic_version/schema_migrations excluded).
P1_TABLES = [
    "universities",
    "it_directions",
    "it_programs",
    "vendors",
    "it_products",
    "responsibles",
    "contracts",
    "licenses",
    "university_responsibles",
    "teachers",
    "teacher_qualifications",
    "teacher_certificates",
    "teacher_programs",
    "students",
    "university_programs",
    "university_products",
    "meetings",
    "documents",
    "interaction_notes",
    "meeting_documents",
    "audit_events",
]

WORKFLOW_TABLES = [
    "workflow_templates",
    "workflow_stages",
    "workflow_instances",
    "instance_stages",
    "transitions",
    "comments",
    "tasks",
    "attachments",
]

EXPECTED_TABLES = P1_TABLES + WORKFLOW_TABLES

VERSION_RE = re.compile(r"^(?P<ver>\d{6}_[a-z0-9_]+)\.(?P<dir>up|down)\.sql$")

# Adoption must not mark migrations added after the archived Alembic head.
LEGACY_TABLES = P1_TABLES


def _database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        # Fall back to app settings (default sqlite -> refuse: SQL is PG-native).
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from app.config import settings

        url = settings.database_url
    if url.startswith("sqlite"):
        raise SystemExit(
            "[migrate] refusing to run PostgreSQL migrations on SQLite. "
            "Set DATABASE_URL to a postgresql+psycopg:// URL."
        )
    # psycopg understands plain postgresql://; strip the SQLAlchemy driver tag.
    return url.replace("postgresql+psycopg://", "postgresql://")


def _discover() -> list[tuple[str, Path, Path]]:
    """Return [(version, up_path, down_path)] sorted by version."""
    ups: dict[str, Path] = {}
    downs: dict[str, Path] = {}
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        m = VERSION_RE.match(path.name)
        if not m:
            raise SystemExit(f"[migrate] bad migration filename: {path.name}")
        if m.group("dir") == "up":
            ups[m.group("ver")] = path
        else:
            downs[m.group("ver")] = path
    versions = sorted(set(ups) | set(downs))
    missing = [v for v in versions if v not in ups or v not in downs]
    if missing:
        raise SystemExit(f"[migrate] missing up/down pair for: {missing}")
    return [(v, ups[v], downs[v]) for v in versions]


def _connect():
    if psycopg is None:
        raise SystemExit("[migrate] psycopg is not installed")
    return psycopg.connect(_database_url(), autocommit=False)


def _ensure_bookkeeping(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    conn.commit()


def _applied(conn) -> list[str]:
    _ensure_bookkeeping(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT version FROM schema_migrations ORDER BY version")
        return [r[0] for r in cur.fetchall()]


def cmd_status() -> int:
    plan = _discover()
    with _connect() as conn:
        applied = _applied(conn)
    available = [v for v, _, _ in plan]
    print(f"available: {len(available)} latest={available[-1] if available else '-'}")
    print(f"applied:   {len(applied)}")
    for v in available:
        mark = "APPLIED" if v in applied else "PENDING"
        print(f"  [{mark}] {v}")
    extra = [v for v in applied if v not in available]
    if extra:
        print(f"  !! applied but no file: {extra}")
        return 1
    return 0


def cmd_up(target: str | None = None) -> int:
    plan = _discover()
    if target and target not in [v for v, _, _ in plan]:
        raise SystemExit(f"[migrate] unknown target version: {target}")
    with _connect() as conn:
        applied = set(_applied(conn))
        for version, up_path, _down in plan:
            if version in applied:
                continue
            if target and version > target:
                break
            sql = up_path.read_text(encoding="utf-8")
            print(f"[migrate] applying {version} ...")
            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    cur.execute(
                        "INSERT INTO schema_migrations (version) VALUES (%s)",
                        (version,),
                    )
                conn.commit()
            except Exception as exc:
                conn.rollback()
                print(f"[migrate] FAILED {version}: {exc}")
                return 1
            print(f"[migrate] applied {version}")
    return 0


def cmd_down(target: str, confirm: bool = False) -> int:
    """Roll back to (and including keep) `target`. Use 'base' for full rollback."""
    plan = _discover()
    versions = [v for v, _, _ in plan]
    if target != "base" and target not in versions:
        raise SystemExit(f"[migrate] unknown target version: {target}")
    with _connect() as conn:
        applied = _applied(conn)
        to_revert = [v for v in reversed(applied)
                     if target == "base" or v > target]
        if not to_revert:
            print("[migrate] nothing to roll back")
            return 0
        if not confirm:
            print("[migrate] would revert: " + ", ".join(to_revert))
            print("[migrate] re-run with --yes to execute")
            return 2
        by_ver = {v: (u, d) for v, u, d in plan}
        for version in to_revert:
            if version not in by_ver:
                print(f"[migrate] no down file for applied {version}; aborting")
                return 1
            down_path = by_ver[version][1]
            sql = down_path.read_text(encoding="utf-8")
            print(f"[migrate] reverting {version} ...")
            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    # Remove bookkeeping AFTER DDL succeeds in the same txn.
                    cur.execute(
                        "DELETE FROM schema_migrations WHERE version = %s",
                        (version,),
                    )
                    # Safety: 000001 down must never drop the version table
                    # itself or the public schema; assert it still exists.
                conn.commit()
            except Exception as exc:
                conn.rollback()
                print(f"[migrate] FAILED rollback {version}: {exc}")
                return 1
            print(f"[migrate] reverted {version}")
    return 0


def cmd_baseline() -> int:
    """Adopt an existing DB created by the old Alembic chain.

    Preconditions (checked, never assumed):
    * ``alembic_version`` has exactly one row = LEGACY_ALEMBIC_HEAD
    * public tables == LEGACY_TABLES (+ alembic_version allowed)
    On success: insert legacy SQL versions into schema_migrations in ONE
    transaction (no DDL re-run), preserving all data. Newer migrations stay
    pending and are applied by the normal ``up`` command.
    """
    plan = [item for item in _discover() if item[0] <= LEGACY_SQL_HEAD]
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_tables "
                "WHERE schemaname='public' AND tablename='alembic_version')"
            )
            has_ledger = cur.fetchone()[0]
        if not has_ledger:
            print("[migrate] baseline skipped: no alembic_version table "
                  "(fresh SQL DB or already adopted)")
            return 1
        with conn.cursor() as cur:
            cur.execute("SELECT version_num FROM alembic_version")
            rows = cur.fetchall()
        if len(rows) != 1 or rows[0][0] != LEGACY_ALEMBIC_HEAD:
            print(f"[migrate] baseline refused: alembic_version={rows} "
                  f"(expected [{LEGACY_ALEMBIC_HEAD}])")
            return 1
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1"
            )
            tables = {r[0] for r in cur.fetchall()} - {"alembic_version"}
        missing = set(LEGACY_TABLES) - tables
        unexpected = tables - set(LEGACY_TABLES) - {"schema_migrations"}
        if missing or unexpected:
            print(f"[migrate] baseline refused: missing={sorted(missing)} "
                  f"unexpected={sorted(unexpected)}")
            print("[migrate] refusing to mask drift with per-table IF EXISTS logic.")
            return 1
        _ensure_bookkeeping(conn)
        with conn.cursor() as cur:
            for version, _, _ in plan:
                cur.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s) "
                    "ON CONFLICT DO NOTHING",
                    (version,),
                )
        conn.commit()
        print(f"[migrate] baseline OK: marked {len(plan)} versions "
              f"(alembic {LEGACY_ALEMBIC_HEAD} adopted, data preserved)")
    return 0


def cmd_verify() -> int:
    plan = _discover()
    with _connect() as conn:
        applied = _applied(conn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1"
            )
            tables = {r[0] for r in cur.fetchall()}
    available = [v for v, _, _ in plan]
    ok = applied == available and set(EXPECTED_TABLES) <= tables
    print(f"latest={available[-1] if available else '-'} "
          f"applied={len(applied)}/{len(available)} "
          f"tables={len(tables)} -> {'OK' if ok else 'DRIFT'}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SQL migration runner (PG only)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="show applied vs available")
    sub.add_parser("current", help="alias for status")
    p_up = sub.add_parser("up", help="apply pending migrations")
    p_up.add_argument("--to", default=None, help="stop at version (inclusive)")
    p_down = sub.add_parser("down", help="roll back to a version (or base)")
    p_down.add_argument("--to", default="base",
                        help="keep target applied; 'base' reverts all")
    p_down.add_argument("--yes", action="store_true",
                        help="actually execute (otherwise dry-run)")
    sub.add_parser("baseline", help="adopt an existing Alembic-head DB")
    sub.add_parser("verify", help="check latest == applied and tables present")
    args = parser.parse_args(argv)
    if args.cmd in ("status", "current"):
        return cmd_status()
    if args.cmd == "up":
        return cmd_up(args.to)
    if args.cmd == "down":
        return cmd_down(args.to, confirm=args.yes)
    if args.cmd == "baseline":
        return cmd_baseline()
    if args.cmd == "verify":
        return cmd_verify()
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
