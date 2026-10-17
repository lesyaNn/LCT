"""PG integration tests for the report statistics (ТЗ charts/graphs).

Two properties are under test, and they are the ones that are easy to get
wrong:

* **the same selection** — the statistics must be computed from exactly the
  rows the table shows for the same filter. Every test compares the
  aggregated counts against the dataset rows it summarises.
* **aggregation in SQL** — the counts must come from ``GROUP BY``, not from
  streaming rows into Python. A statement counter proves the number of
  statements stays constant as the data grows.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.security import CurrentUser
from app.models.catalog import (
    ITDirection,
    ITProduct,
    ITProgram,
    License,
    Responsible,
    University,
    UniversityResponsible,
    Vendor,
)
from app.models.interactions import Meeting, UniversityProduct
from app.modules.analytics.dataset import ReportDatasetService
from app.modules.analytics.filters import UnifiedFilter
from app.modules.analytics.stats import NO_VALUE_LABEL, ReportStatsService
from tests.db_helpers import require_pg_engine

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")
TODAY = date(2026, 9, 20)
SEPTEMBER = UnifiedFilter(date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def session():
    eng = require_pg_engine(TEST_URL)
    with Session(eng) as s:
        yield s
    eng.dispose()


@pytest.fixture()
def data(session):
    """Two directions, two products, two responsibles, three universities.

    * ``alpha`` 3 licenses: 2 of product A + 1 of product B, direction A;
    * ``beta``  1 license of product A with **no** direction, so its row must
      land in the ``Без данных`` bucket instead of being dropped;
    * ``gamma`` only an August meeting, so the September period excludes it
      entirely — it also has no license, so it proves the period narrows
      before the row grain is applied.
    """
    d_a = ITDirection(id=uuid4(), code="SA", name="Направление А")
    d_b = ITDirection(id=uuid4(), code="SB", name="Направление Б")
    p_a = ITProgram(id=uuid4(), direction_id=d_a.id, name="Программа А")
    vendor = Vendor(id=uuid4(), name="Вендор")
    prod_a = ITProduct(id=uuid4(), vendor_id=vendor.id, name="ПО А")
    prod_b = ITProduct(id=uuid4(), vendor_id=vendor.id, name="ПО Б")
    r_ivan = Responsible(id=uuid4(), full_name="Иван Петров", email="ivan@x.local")
    r_petr = Responsible(id=uuid4(), full_name="Пётр Сидоров", email="petr@x.local")
    alpha = University(id=uuid4(), name="ВУЗ Альфа", created_at=_utc(2026, 6, 1))
    beta = University(id=uuid4(), name="ВУЗ Бета", created_at=_utc(2026, 6, 1))
    gamma = University(id=uuid4(), name="ВУЗ Гамма", created_at=_utc(2026, 6, 1))
    session.add_all(
        [d_a, d_b, p_a, vendor, prod_a, prod_b, r_ivan, r_petr, alpha, beta, gamma]
    )
    session.flush()
    session.add_all([
        Meeting(
            id=uuid4(), university_id=u.id, meeting_type="online", subject="Встреча",
            participants=[], meeting_at=_utc(2026, 9, 10), created_by_keycloak_sub="t",
        )
        for u in (alpha, beta)
    ])
    # Gamma interacts only in August, so a September period must exclude it.
    session.add(Meeting(
        id=uuid4(), university_id=gamma.id, meeting_type="offline",
        subject="Августовская встреча", participants=[],
        meeting_at=_utc(2026, 8, 10), created_by_keycloak_sub="t",
    ))
    session.add_all([
        UniversityResponsible(university_id=alpha.id, responsible_id=r_ivan.id),
        UniversityResponsible(university_id=alpha.id, responsible_id=r_petr.id),
        UniversityResponsible(university_id=beta.id, responsible_id=r_ivan.id),
        UniversityProduct(university_id=alpha.id, product_id=prod_a.id),
    ])

    def _lic(university, product, program, direction, number):
        """``program``/``direction`` accept the model or None."""
        return License(
            id=uuid4(), university_id=university.id, product_id=product.id,
            contract_id=None,
            program_id=program.id if program is not None else None,
            direction_id=direction.id if direction is not None else None,
            license_number=number, signed_at=date(2026, 6, 1),
            expires_at=date(2027, 6, 1), transfer_status_raw="transferred",
            comment=None,
        )

    session.add_all([
        _lic(alpha, prod_a, p_a, d_a, "A-1"),
        _lic(alpha, prod_a, p_a, d_a, "A-2"),
        _lic(alpha, prod_b, p_a, d_a, "A-3"),
        # Beta has no program and no direction: its row is the NULL bucket.
        _lic(beta, prod_a, None, None, "B-1"),
    ])
    session.commit()
    return {
        "alpha": alpha, "beta": beta, "gamma": gamma,
        "prod_a": prod_a, "prod_b": prod_b, "d_a": d_a, "d_b": d_b,
    }


def _buckets(stats, dimension):
    item = stats.slice(dimension)
    assert item is not None, dimension
    return dict(item.buckets and {b.label: b.count for b in item.buckets})


# ------------------------------------------------------------- the selection


def test_statistics_use_the_same_selection_as_the_table(session, data):
    stats = ReportStatsService.build(session, SEPTEMBER, today=TODAY)
    ds = ReportDatasetService.fetch_rows(
        session, SEPTEMBER, ["university", "product"], today=TODAY
    )
    assert stats.row_count == ds.total
    assert stats.university_count == len(ds.university_ids)


def test_period_narrows_the_selection_the_same_way_for_both(session, data):
    """A university whose only interaction is in August stays out."""
    stats = ReportStatsService.build(session, SEPTEMBER, today=TODAY)
    ds = ReportDatasetService.fetch_rows(
        session, SEPTEMBER, ["university", "product"], today=TODAY
    )
    assert data["gamma"].name not in {r["university"] for r in ds.rows}
    assert stats.university_count == 2


def test_empty_selection_produces_empty_statistics_not_an_error(session, data):
    stats = ReportStatsService.build(
        session, UnifiedFilter(date_from=date(2020, 1, 1), date_to=date(2020, 1, 2))
    )
    assert stats.row_count == 0
    assert stats.university_count == 0
    for item in stats.slices:
        assert item.buckets == ()
        assert item.total == 0


# ---------------------------------------------------------------- the counts


def test_direction_buckets_add_up_to_the_row_count(session, data):
    stats = ReportStatsService.build(session, SEPTEMBER, today=TODAY)
    item = stats.slice("by_direction")
    assert item is not None
    assert item.unit == "rows"
    # Never lose a row to a NULL label: the buckets must sum to the total.
    assert sum(b.count for b in item.buckets) == stats.row_count
    assert _buckets(stats, "by_direction") == {"Направление А": 3, NO_VALUE_LABEL: 1}


def test_product_buckets_add_up_to_the_row_count(session, data):
    stats = ReportStatsService.build(session, SEPTEMBER, today=TODAY)
    assert sum(b.count for b in stats.slice("by_product").buckets) == stats.row_count
    assert _buckets(stats, "by_product") == {"ПО А": 3, "ПО Б": 1}


def test_workflow_status_falls_back_to_no_data_when_absent(session, data):
    """No workflow rows were seeded, so the status column is NULL for all."""
    stats = ReportStatsService.build(session, SEPTEMBER, today=TODAY)
    assert _buckets(stats, "by_workflow_status") == {NO_VALUE_LABEL: stats.row_count}


def test_responsible_counts_distinct_universities(session, data):
    """A university with two responsibles is counted once for each of them."""
    stats = ReportStatsService.build(session, SEPTEMBER, today=TODAY)
    item = stats.slice("by_responsible")
    assert item is not None
    # Documented, different grain from the row-grain dimensions.
    assert item.unit == "universities"
    assert dict((b.label, b.count) for b in item.buckets) == {
        "Иван Петров": 2,   # alpha + beta
        "Пётр Сидоров": 1,  # alpha only
    }
    assert item.total == 3  # two links, three distinct universities, no double count


def test_buckets_are_ordered_by_count_desc_then_label(session, data):
    stats = ReportStatsService.build(session, SEPTEMBER, today=TODAY)
    for item in stats.slices:
        keys = [(-b.count, b.label) for b in item.buckets]
        assert keys == sorted(keys), item.dimension


def test_long_tail_keeps_every_product_bucket(session, data):
    """The chart can scroll through every product without an aggregate tail."""
    products = [
        ITProduct(id=uuid4(), vendor_id=data["prod_a"].vendor_id, name=f"ПО {index:02d}")
        for index in range(11)
    ]
    session.add_all(products)
    session.flush()
    session.add_all([
        License(
            id=uuid4(), university_id=data["alpha"].id, product_id=product.id,
            contract_id=None, program_id=None, direction_id=None,
            license_number=f"EXTRA-{index}", signed_at=date(2026, 6, 1),
            expires_at=date(2027, 6, 1), transfer_status_raw="transferred",
            comment=None,
        )
        for index, product in enumerate(products)
    ])
    session.commit()
    stats = ReportStatsService.build(session, SEPTEMBER, today=TODAY)
    item = stats.slice("by_product")
    assert item is not None
    assert len(item.buckets) == 13
    assert {bucket.label for bucket in item.buckets} == {
        "ПО А", "ПО Б", *(product.name for product in products),
    }
    assert item.total == sum(bucket.count for bucket in item.buckets) == stats.row_count


# --------------------------------------------------------------------- scope


def test_statistics_respect_the_security_scope(session, data):
    user = CurrentUser(
        id="scoped", roles={"manager"}, university_ids=(str(data["beta"].id),)
    )
    stats = ReportStatsService.build(session, SEPTEMBER, user=user, today=TODAY)
    assert stats.university_count == 1
    assert stats.row_count == 1
    assert _buckets(stats, "by_product") == {"ПО А": 1}


def test_scope_can_only_narrow_never_widen(session, data):
    user = CurrentUser(
        id="scoped", roles={"manager"}, university_ids=(str(data["gamma"].id),)
    )
    scoped = ReportStatsService.build(session, SEPTEMBER, user=user, today=TODAY)
    full = ReportStatsService.build(session, SEPTEMBER, today=TODAY)
    assert scoped.row_count <= full.row_count
    assert scoped.university_count <= full.university_count


# -------------------------------------------------------------- SQL, not rows


def test_statements_stay_constant_as_data_grows(session, data):
    """The count is GROUP BY, not a Python loop over the rows."""
    counting = {"on": False}
    counter = {"n": 0, "log": []}

    def _count(conn, cursor, statement, parameters, context, executemany):
        # Only reads issued while the measurement window is open, so the
        # fixture's own INSERTs and the harness schema probes stay out.
        if counting["on"] and statement.lstrip().upper().startswith("SELECT"):
            counter["n"] += 1
            counter["log"].append(" ".join(statement.split())[:80])

    event.listen(session.get_bind(), "before_cursor_execute", _count)
    try:
        small = ReportStatsService.build(session, SEPTEMBER, today=TODAY)
        for i in range(30):
            session.add(License(
                id=uuid4(), university_id=data["alpha"].id,
                product_id=data["prod_a"].id, contract_id=None, program_id=None,
                direction_id=data["d_a"].id, license_number=f"EXTRA-{i}",
                signed_at=date(2026, 6, 1), expires_at=date(2027, 6, 1),
                transfer_status_raw="transferred", comment=None,
            ))
        session.commit()
        counter["n"], counter["log"] = 0, []
        counting["on"] = True
        after = ReportStatsService.build(session, SEPTEMBER, today=TODAY)
        counting["on"] = False
    finally:
        event.remove(session.get_bind(), "before_cursor_execute", _count)

    # 30 extra rows, same number of statements -> the counting is in SQL.
    assert after.row_count == small.row_count + 30
    # 2 counts + 3 label aggregations + 1 responsible aggregation.
    assert counter["n"] == 6, f"unexpected statements: {counter['n']}\n" + "\n".join(
        counter["log"]
    )


# --------------------------------------------------------------- HTTP shape


def test_statistics_endpoint_returns_labels_not_ids(session, data):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.core.errors import register_error_handlers
    from app.core.security import get_current_user
    from app.modules.analytics.stats_router import router as stats_router
    from app.modules.audit.service import get_audit_db

    api = FastAPI()
    register_error_handlers(api)
    api.include_router(stats_router)
    user = CurrentUser(id="admin", roles={"admin", "*"}, university_ids=None)
    api.dependency_overrides[get_current_user] = lambda: user
    api.dependency_overrides[get_audit_db] = lambda: session
    client = TestClient(api, raise_server_exceptions=False)

    response = client.post(
        "/reports/statistics",
        json={"filters": {"date_from": "2026-09-01", "date_to": "2026-09-30"}},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["university_count"] == 2
    assert payload["row_count"] == 4
    assert payload["columns"]  # echoed for labelling
    labels = {b["label"] for s in payload["slices"] for b in s["buckets"]}
    assert "Направление А" in labels
    # Human-readable names, never raw identifiers.
    assert all(not label.count("-") >= 8 for label in labels)


def test_statistics_endpoint_rejects_a_reversed_period(session, data):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.core.errors import register_error_handlers
    from app.core.security import get_current_user
    from app.modules.analytics.stats_router import router as stats_router
    from app.modules.audit.service import get_audit_db

    api = FastAPI()
    register_error_handlers(api)
    api.include_router(stats_router)
    user = CurrentUser(id="admin", roles={"admin", "*"}, university_ids=None)
    api.dependency_overrides[get_current_user] = lambda: user
    api.dependency_overrides[get_audit_db] = lambda: session
    client = TestClient(api, raise_server_exceptions=False)

    response = client.post(
        "/reports/statistics",
        json={"filters": {"date_from": "2026-09-30", "date_to": "2026-09-01"}},
    )
    assert response.status_code == 422, response.text
