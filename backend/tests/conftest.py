"""Shared fixtures for P1 seed tests (P1-09-0x).

``seeded_db``: fresh SQLite database with the full idempotent demo seed
(``app.db.seed.seed_demo``) applied — the same dataset P3 mocks and demo
scenarios are built from.
"""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (register metadata)
from app.db.base import Base
from app.db.seed import seed_demo


@pytest.fixture()
def seeded_db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/seed.db")

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_conn, _rec):  # pragma: no cover
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    with Session(eng) as session:
        seed_demo(session)
        yield session
    eng.dispose()
