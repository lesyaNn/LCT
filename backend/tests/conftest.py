"""Shared fixtures for P1 seed tests (P1-09-0x)."""

import os

import pytest
from sqlalchemy.orm import Session

from app.db.seed import seed_demo


@pytest.fixture()
def seeded_db(tmp_path):
    from tests.db_helpers import require_pg_engine

    eng = require_pg_engine(os.getenv("TEST_DATABASE_URL", "sqlite://"))
    with Session(eng) as session:
        seed_demo(session)
        yield session
    eng.dispose()
