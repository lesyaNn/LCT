"""M6: test-DB isolation guards (pure-unit, no database).

Pins fail-closed behaviour of the destructive test reset path:
* ``assert_dedicated_test_db`` refuses PG URLs whose DB name lacks "test";
* ``reset_test_db`` refuses SQLite / non-PostgreSQL engines without touching
  the database;
* ``require_pg_engine`` skips (never emulates) without a PostgreSQL URL.
"""

import pytest
from sqlalchemy import create_engine

from tests.db_helpers import assert_dedicated_test_db, reset_test_db, require_pg_engine


def test_test_db_name_guard_accepts_test_names():
    assert_dedicated_test_db("postgresql+psycopg://u:p@localhost:5432/rtk_test") == "rtk_test"
    assert_dedicated_test_db("postgresql://u@localhost:5432/TEST_db?sslmode=require")


def test_test_db_name_guard_refuses_prod_like_names():
    for url in (
        "postgresql+psycopg://u:p@localhost:5432/rtk",
        "postgresql://u@localhost:5432/postgres",
        "postgresql+psycopg://u:p@localhost:5432/keycloak",
    ):
        with pytest.raises(SystemExit):
            assert_dedicated_test_db(url)


def test_reset_refuses_sqlite_without_touching_db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/unit.db")
    try:
        with pytest.raises(SystemExit):
            reset_test_db(eng, f"sqlite:///{tmp_path}/unit.db")
    finally:
        eng.dispose()


def test_require_pg_engine_skips_without_postgresql(monkeypatch):
    monkeypatch.setenv("TEST_DATABASE_URL", "sqlite://")
    with pytest.raises(pytest.skip.Exception):
        require_pg_engine("sqlite://")


def test_require_pg_engine_refuses_non_test_pg_name():
    # Fail-closed (SystemExit), not a skip: a PG URL at a prod-like name
    # must never reach DROP SCHEMA.
    with pytest.raises(SystemExit):
        require_pg_engine("postgresql+psycopg://u:p@localhost:5432/rtk")
