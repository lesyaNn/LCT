"""P2-07-03: компонент D — unit + DB тесты (только P1 documents)."""

import os
from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

import app.models  # noqa: F401 (register metadata)
from app.models.catalog import University
from app.models.interactions import Document
from app.modules.health_score.documents_score import (
    calc_D,
    is_document_valid,
    required_document_types,
    score_documents,
)

TODAY = date(2026, 9, 20)

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")


@pytest.fixture()
def engine():
    """PostgreSQL integration DB (canonical SQL migrations; skips w/o PG)."""
    from tests.db_helpers import require_pg_engine

    eng = require_pg_engine(TEST_URL)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    with Session(engine) as session:
        yield session


def test_required_types_default_and_env():
    assert required_document_types(None) == frozenset(
        {"contract", "license", "act", "protocol"}
    )
    assert required_document_types("") == frozenset(
        {"contract", "license", "act", "protocol"}
    )
    assert required_document_types("contract, act") == frozenset({"contract", "act"})


def test_is_document_valid():
    assert is_document_valid("signed", None, TODAY)
    assert is_document_valid("active", TODAY, TODAY)
    assert is_document_valid("signed", TODAY + timedelta(days=1), TODAY)
    assert not is_document_valid("signed", TODAY - timedelta(days=1), TODAY)
    assert not is_document_valid("draft", None, TODAY)
    assert not is_document_valid("archived", None, TODAY)


def test_score_documents_empty_is_100():
    assert score_documents([], TODAY) == (100, 0, 0)


def test_score_documents_rounding_and_other_type_ignored_by_caller():
    items = [
        {"status_raw": "signed", "expires_at": None},
        {"status_raw": "signed", "expires_at": TODAY - timedelta(days=1)},
        {"status_raw": "draft", "expires_at": None},
    ]
    assert score_documents(items, TODAY) == (33, 1, 3)


def test_calc_D_db_single_query_no_required_is_100(db):
    uni = University(id=uuid4(), name="Вуз D-1")
    db.add(uni)
    db.commit()
    assert calc_D(db, uni.id, TODAY) == (100, 0, 0)


def test_calc_D_db_counts_only_required_types(db):
    uni = University(id=uuid4(), name="Вуз D-2")
    db.add(uni)
    db.flush()
    docs = [
        Document(
            id=uuid4(), university_id=uni.id, document_type="contract",
            title="Договор", file_path="/f/1", file_name="d.pdf",
            status_raw="signed", expires_at=None,
            uploaded_by_keycloak_sub="t",
        ),
        Document(
            id=uuid4(), university_id=uni.id, document_type="license",
            title="Лицензия", file_path="/f/2", file_name="l.pdf",
            status_raw="signed", expires_at=TODAY - timedelta(days=1),
            uploaded_by_keycloak_sub="t",
        ),
        Document(
            id=uuid4(), university_id=uni.id, document_type="other",
            title="Прочее", file_path="/f/3", file_name="o.pdf",
            status_raw="draft", expires_at=None,
            uploaded_by_keycloak_sub="t",
        ),
    ]
    db.add_all(docs)
    db.commit()
    # other игнорируется: total=2, valid=1 → 50
    assert calc_D(db, uni.id, TODAY) == (50, 1, 2)
