"""Test database setup — PostgreSQL via canonical SQL migrations ONLY.

There is deliberately NO SQLite / create_all / drop_all path here.
``backend/migrations/*.up.sql`` applied by ``scripts/migrate.py`` is the
sole schema source; Python never creates, alters, or drops schema —
not in production, not in tests.

* DB integration tests use :func:`require_pg_engine`, which skips unless
  ``TEST_DATABASE_URL`` points at PostgreSQL.
* Tests that need no schema at all (pure-unit: enum parsing, formulas,
  readiness math, OpenAPI shape) take no ``engine``/``db`` fixture and
  keep running everywhere.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text


def _load_migrate_module():
    path = Path(__file__).resolve().parent.parent / "scripts" / "migrate.py"
    spec = importlib.util.spec_from_file_location("sql_migrate", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reset_test_db(engine, url: str) -> None:
    """Reset a PostgreSQL test engine to a clean canonical schema.

    Drops ``public`` (test-only, dedicated test database), recreates it,
    then applies ALL SQL migrations via the canonical runner (fresh-DB path).
    Refuses non-PostgreSQL URLs: there is no second schema path.
    """
    if engine.dialect.name != "postgresql":
        raise SystemExit(
            "reset_test_db supports PostgreSQL only — SQL migrations are "
            "PostgreSQL-native and the sole schema source."
        )
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    migrate = _load_migrate_module()
    old = os.getenv("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        rc = migrate.cmd_up()
    finally:
        if old is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old
    assert rc == 0, "SQL migrations failed in test setup"


def require_pg_engine(url: str):
    """Create a fresh PG test engine or skip (no SQLite fallback).

    Every DB integration test in this repo is a PostgreSQL integration
    test. Without ``TEST_DATABASE_URL=postgresql+psycopg://...`` the test
    is skipped — never emulated via ORM DDL.
    """
    if not url.startswith("postgresql"):
        pytest.skip(
            "requires TEST_DATABASE_URL=postgresql+psycopg://... "
            "(SQL migrations are the sole schema source; no SQLite DDL path)"
        )
    eng = create_engine(url)
    reset_test_db(eng, url)
    return eng
