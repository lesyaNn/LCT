"""Shared fixtures for P1 seed tests (P1-09-0x).

Isolation (M6): every ``seeded_db`` consumer gets a FRESH canonical schema
(``reset_test_db``: DROP SCHEMA + full SQL ``up``) on a DEDICATED PostgreSQL
test database. The DB name guard (``assert_dedicated_test_db``) refuses to
wipe non-test databases fail-closed. The seed runs inside the fixture and
the session is rolled back + the engine disposed on teardown, so tests
cannot leak rows into each other even if a test forgets ``rollback``.
"""

import os

import pytest
from sqlalchemy.orm import Session

from app.db.seed import seed_demo


@pytest.fixture()
def seeded_db(tmp_path):
    from tests.db_helpers import assert_dedicated_test_db, require_pg_engine

    url = os.getenv("TEST_DATABASE_URL", "sqlite://")
    if url.startswith("postgresql"):
        # Fail closed BEFORE any engine work: never wipe a non-test DB.
        assert_dedicated_test_db(url)
    eng = require_pg_engine(url)
    try:
        with Session(eng) as session:
            seed_demo(session)
            yield session
            session.rollback()
    finally:
        eng.dispose()
