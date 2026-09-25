"""P5 scope integration against migrated PostgreSQL 16 only."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.policies import apply_university_scope, ensure_university_access
from app.core.security import CurrentUser
from app.models.catalog import University
from app.modules.catalog import service


@pytest.fixture()
def pg():
    from tests.db_helpers import require_pg_engine

    engine = require_pg_engine(os.getenv("TEST_DATABASE_URL", "sqlite://"))
    try:
        yield engine
    finally:
        engine.dispose()


def _user(role, ids=None):
    return CurrentUser(id="p5-actor", roles={role}, university_ids=ids)


def test_collection_count_filter_object_and_empty_scope(pg):
    rows = [University(id=uuid4(), name=f"P5 University {i}") for i in range(5)]
    with Session(pg) as db:
        db.add_all(rows)
        db.commit()
        visible = _user("user", (str(rows[1].id), str(rows[3].id)))

        def page(actor, unified=None):
            return service.list_university_page(
                db, page=1, page_size=20, search=None, city=None,
                responsible_id=None, sort_by="name", sort_order="asc",
                unified_filter=unified, user=actor,
            )

        items, total = page(visible)
        assert total == 2
        assert {item.id for item in items} == {rows[1].id, rows[3].id}
        assert page(_user("manager", ()))[1] == 0
        assert page(_user("user"))[1] == 0
        assert page(_user("admin"))[1] == 5

        from app.modules.analytics.filters import UnifiedFilter

        foreign_filter = UnifiedFilter(university_ids=[rows[0].id])
        assert page(visible, foreign_filter)[1] == 0
        assert page(visible, foreign_filter)[0] == []

        scoped_ids = db.scalars(apply_university_scope(
            select(University.id), University.id, visible
        )).all()
        assert set(scoped_ids) == {rows[1].id, rows[3].id}
        ensure_university_access(rows[1].id, visible)
        from app.core.errors import SecurityError

        with pytest.raises(SecurityError):
            ensure_university_access(rows[0].id, visible)
