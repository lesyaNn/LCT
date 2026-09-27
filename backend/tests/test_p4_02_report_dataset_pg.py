"""P4-02-01/02-02 PostgreSQL tests: report dataset over the frozen UnifiedFilter.

Deterministic fixture (extends the P4-01-01 shape with business rows):

* Uni Alpha (2026-01-10): programs p1+p2 (direction d1), product prod1,
  responsible r1; licenses L-001 (prod1/p1/d1, contract C-001) + L-002
  (prod2/p2, direction via program fallback, NO contract); workflow with a
  completed stage + an overdue pending current stage ("Stage 2").
* Uni Beta (2026-05-20): program p3 (d2), product prod2, responsible r2;
  license L-003 (prod2/p3/d2, contract C-002); workflow with a future
  pending current stage ("Stage 1").
* Uni Gamma (2026-08-01): no links, no licenses, standalone contract C-003
  (fallback contract row), no workflow, no snapshots.
* Uni Delta (2026-03-15): product prod1, responsibles r1+r2, no programs,
  no licenses/contracts; workflow with a skipped + a future pending stage.
* Uni Epsilon (2026-04-10): program p1 (d1, status planned), nothing else;
  workflow_status falls back to the UniversityProgram status.

Health snapshots: Alpha 70 (old) + 85 (latest); Beta 60; the rest none.

Row grain under test: one row per (University x License) + one fallback
row per license-less university = 3 licenses + 3 fallbacks = 6 rows.
Requires ``TEST_DATABASE_URL=postgresql+psycopg://...`` (skipped otherwise).
"""

import os
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

import app.models  # noqa: F401 (register metadata)
from app.core.security import CurrentUser
from app.models.catalog import (
    Contract,
    ITDirection,
    ITProduct,
    ITProgram,
    License,
    Responsible,
    University,
    UniversityResponsible,
    Vendor,
)
from app.models.interactions import UniversityProduct, UniversityProgram
from app.models.workflow_instances import InstanceStage, WorkflowInstance
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate
from app.modules.analytics.analytics import AnalyticsService
from app.modules.analytics.columns import (
    MANDATORY_COLUMNS,
    EmptyReportColumnsError,
    UnknownReportColumnError,
)
from app.modules.analytics.dataset import ReportDatasetService as Dataset
from app.modules.analytics.filter_service import UnifiedFilterService
from app.modules.analytics.filters import UnifiedFilter
from app.schemas.common import WorkflowStageStatus

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")
TODAY = date(2026, 9, 20)


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def fx():
    """Fresh PG schema + deterministic seed; yields (session, ids)."""
    from tests.db_helpers import require_pg_engine

    eng = require_pg_engine(TEST_URL)
    with Session(eng) as session:
        ids = _seed(session)
        session.commit()
        yield session, eng, ids
    eng.dispose()


@pytest.fixture()
def select_counter(fx):
    _, eng, _ = fx
    count = {"n": 0}

    @event.listens_for(eng, "before_cursor_execute")
    def _count(conn, cursor, statement, params, context, executemany):
        if statement.strip().upper().startswith("SELECT"):
            count["n"] += 1

    yield count
    event.remove(eng, "before_cursor_execute", _count)


def _seed(s: Session) -> dict:
    d1 = ITDirection(id=uuid4(), code="D1", name="Direction One")
    d2 = ITDirection(id=uuid4(), code="D2", name="Direction Two")
    p1 = ITProgram(id=uuid4(), direction_id=d1.id, name="Program 1")
    p2 = ITProgram(id=uuid4(), direction_id=d1.id, name="Program 2")
    p3 = ITProgram(id=uuid4(), direction_id=d2.id, name="Program 3")
    vendor = Vendor(id=uuid4(), name="Vendor V")
    prod1 = ITProduct(id=uuid4(), vendor_id=vendor.id, name="Product 1")
    prod2 = ITProduct(id=uuid4(), vendor_id=vendor.id, name="Product 2")
    r1 = Responsible(id=uuid4(), full_name="Resp One", email="r1@x.local")
    r2 = Responsible(id=uuid4(), full_name="Resp Two", email="r2@x.local")
    alpha = University(id=uuid4(), name="Uni Alpha", created_at=_utc(2026, 1, 10))
    beta = University(id=uuid4(), name="Uni Beta", created_at=_utc(2026, 5, 20))
    gamma = University(id=uuid4(), name="Uni Gamma", created_at=_utc(2026, 8, 1))
    delta = University(id=uuid4(), name="Uni Delta", created_at=_utc(2026, 3, 15))
    epsilon = University(id=uuid4(), name="Uni Epsilon", created_at=_utc(2026, 4, 10))
    s.add_all(
        [d1, d2, p1, p2, p3, vendor, prod1, prod2, r1, r2,
         alpha, beta, gamma, delta, epsilon]
    )
    s.flush()
    s.add_all(
        [
            UniversityProgram(university_id=alpha.id, program_id=p1.id),
            UniversityProgram(university_id=alpha.id, program_id=p2.id),
            UniversityProgram(university_id=beta.id, program_id=p3.id),
            UniversityProgram(university_id=epsilon.id, program_id=p1.id),
            UniversityProduct(university_id=alpha.id, product_id=prod1.id),
            UniversityProduct(university_id=beta.id, product_id=prod2.id),
            UniversityProduct(university_id=delta.id, product_id=prod1.id),
            UniversityResponsible(university_id=alpha.id, responsible_id=r1.id),
            UniversityResponsible(university_id=beta.id, responsible_id=r2.id),
            UniversityResponsible(university_id=delta.id, responsible_id=r1.id),
            UniversityResponsible(university_id=delta.id, responsible_id=r2.id),
        ]
    )
    s.add_all([
        HealthScoreCurrent(university_id=alpha.id, score=85, status="green",
                           breakdown={}, reasons=[], input_counters={},
                           calculated_at=datetime(2026, 9, 1, tzinfo=timezone.utc)),
        HealthScoreCurrent(university_id=beta.id, score=60, status="yellow",
                           breakdown={}, reasons=[], input_counters={},
                           calculated_at=datetime(2026, 9, 1, tzinfo=timezone.utc)),
    ])
    c1 = Contract(
        id=uuid4(), university_id=alpha.id, contract_number="C-001",
        product_id=prod1.id, signed_at=date(2026, 1, 20),
        expires_at=date(2027, 1, 20), transfer_status_raw="accepted",
        comment="C1 comment",
    )
    c2 = Contract(
        id=uuid4(), university_id=beta.id, contract_number="C-002",
        product_id=prod2.id, signed_at=date(2026, 4, 1),
        expires_at=date(2028, 4, 1), transfer_status_raw="transferred",
        comment=None,
    )
    c3 = Contract(
        id=uuid4(), university_id=gamma.id, contract_number="C-003",
        product_id=None, signed_at=date(2026, 7, 1),
        expires_at=date(2027, 7, 1), transfer_status_raw="pending",
        comment="C3 comment",
    )
    s.add_all([c1, c2, c3])
    s.flush()
    s.add_all(
        [
            License(
                id=uuid4(), university_id=alpha.id, product_id=prod1.id,
                contract_id=c1.id, program_id=p1.id, direction_id=d1.id,
                license_number="L-001", signed_at=date(2026, 2, 1),
                expires_at=date(2027, 2, 1), transfer_status_raw="transferred",
                comment="L1 comment",
            ),
            License(
                id=uuid4(), university_id=alpha.id, product_id=prod2.id,
                contract_id=None, program_id=p2.id, direction_id=None,
                license_number="L-002", signed_at=date(2026, 3, 1),
                expires_at=date(2026, 9, 1), transfer_status_raw="pending",
                comment=None,
            ),
            License(
                id=uuid4(), university_id=beta.id, product_id=prod2.id,
                contract_id=c2.id, program_id=p3.id, direction_id=d2.id,
                license_number="L-003", signed_at=date(2026, 4, 15),
                expires_at=date(2028, 4, 15), transfer_status_raw="accepted",
                comment="L3 comment",
            ),
        ]
    )
    template = WorkflowTemplate(id=uuid4(), name="Template T")
    s.add(template)
    s.flush()
    t1 = WorkflowStage(template_id=template.id, name="Stage 1", order_index=1)
    t2 = WorkflowStage(template_id=template.id, name="Stage 2", order_index=2)
    s.add_all([t1, t2])
    s.flush()
    inst_a = WorkflowInstance(university_id=alpha.id, template_id=template.id)
    inst_b = WorkflowInstance(university_id=beta.id, template_id=template.id)
    inst_d = WorkflowInstance(university_id=delta.id, template_id=template.id)
    s.add_all([inst_a, inst_b, inst_d])
    s.flush()
    st_a1 = InstanceStage(
        instance_id=inst_a.id, template_stage_id=t1.id, order_index=1,
        name="Stage 1", status="completed",
        completed_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    st_a2 = InstanceStage(
        instance_id=inst_a.id, template_stage_id=t2.id, order_index=2,
        name="Stage 2", status="pending", due_date=date(2026, 9, 10),
    )
    st_b1 = InstanceStage(
        instance_id=inst_b.id, template_stage_id=t1.id, order_index=1,
        name="Stage 1", status="pending", due_date=date(2026, 12, 1),
    )
    st_d1 = InstanceStage(
        instance_id=inst_d.id, template_stage_id=t1.id, order_index=1,
        name="Stage 1", status="skipped",
        completed_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )
    st_d2 = InstanceStage(
        instance_id=inst_d.id, template_stage_id=t2.id, order_index=2,
        name="Stage 2", status="pending", due_date=date(2026, 12, 15),
    )
    s.add_all([st_a1, st_a2, st_b1, st_d1, st_d2])
    s.flush()
    inst_a.current_instance_stage_id = st_a2.id
    inst_a.current_stage_id = t2.id
    inst_b.current_instance_stage_id = st_b1.id
    inst_b.current_stage_id = t1.id
    inst_d.current_instance_stage_id = st_d2.id
    inst_d.current_stage_id = t2.id
    s.add_all(
        [
            HealthScoreSnapshot(
                id=uuid4(), university_id=alpha.id, score=70, status="yellow",
                breakdown={}, reasons=[],
                calculated_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
                period_day=date(2026, 8, 1), trigger_event="daily_cron",
            ),
            HealthScoreSnapshot(
                id=uuid4(), university_id=alpha.id, score=85, status="green",
                breakdown={}, reasons=[],
                calculated_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
                period_day=date(2026, 9, 1), trigger_event="daily_cron",
            ),
            HealthScoreSnapshot(
                id=uuid4(), university_id=beta.id, score=60, status="yellow",
                breakdown={}, reasons=[],
                calculated_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
                period_day=date(2026, 9, 1), trigger_event="daily_cron",
            ),
        ]
    )
    return {
        "d1": d1.id, "d2": d2.id,
        "p1": p1.id, "p2": p2.id, "p3": p3.id,
        "prod1": prod1.id, "prod2": prod2.id,
        "r1": r1.id, "r2": r2.id,
        "alpha": alpha.id, "beta": beta.id, "gamma": gamma.id,
        "delta": delta.id, "epsilon": epsilon.id,
    }


def _fetch(s: Session, f: UnifiedFilter, columns=None, **kw):
    return Dataset.fetch_rows(s, f, columns, today=TODAY, **kw)


def _by_uni(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for row in rows:
        out.setdefault(row["university"], []).append(row)
    return out


# ------------------------------------------------------- 14 column values


def test_default_columns_are_14_mandatory(fx):
    s, _, _ = fx
    ds = _fetch(s, UnifiedFilter(), None)
    assert ds.columns == list(MANDATORY_COLUMNS)
    assert all(set(row.keys()) == set(MANDATORY_COLUMNS) for row in ds.rows)


def test_license_row_full_values(fx):
    s, _, _ = fx
    ds = _fetch(s, UnifiedFilter(), None)
    rows = _by_uni(ds.rows)["Uni Alpha"]
    lic1 = next(r for r in rows if r["contract_number"] == "C-001")
    assert lic1["university"] == "Uni Alpha"
    assert lic1["direction"] == "Direction One"
    assert lic1["program"] == "Program 1"
    assert lic1["product"] == "Product 1"
    assert lic1["vendor"] == "Vendor V"
    assert lic1["license_signed"] == date(2026, 2, 1)
    assert lic1["license_expires"] == date(2027, 2, 1)
    assert lic1["transfer_status"] == "transferred"
    assert lic1["comment"] == "L1 comment"
    assert lic1["responsible"] == "Resp One"
    assert lic1["workflow_status"] == "Stage 2"  # current stage wins
    assert lic1["health_score"] == 85  # latest snapshot, not 70


def test_license_without_contract_nulls(fx):
    s, _, _ = fx
    ds = _fetch(s, UnifiedFilter(), None)
    rows = _by_uni(ds.rows)["Uni Alpha"]
    lic2 = next(r for r in rows if r["license_expires"] == date(2026, 9, 1))
    assert lic2["contract_number"] is None
    assert lic2["comment"] is None
    assert lic2["direction"] == "Direction One"  # via program fallback
    assert lic2["program"] == "Program 2"
    assert lic2["product"] == "Product 2"


def test_fallback_row_uses_latest_contract(fx):
    s, _, _ = fx
    ds = _fetch(s, UnifiedFilter(), None)
    rows = _by_uni(ds.rows)["Uni Gamma"]
    assert len(rows) == 1
    row = rows[0]
    assert row["contract_number"] == "C-003"
    assert row["transfer_status"] == "pending"
    assert row["comment"] == "C3 comment"
    assert row["license_signed"] is None
    assert row["license_expires"] is None
    assert row["direction"] is None
    assert row["program"] is None
    assert row["product"] is None
    assert row["vendor"] is None
    assert row["responsible"] is None
    assert row["workflow_status"] is None
    assert row["health_score"] is None


def test_all_null_fallback_row(fx):
    s, _, _ = fx
    ds = _fetch(s, UnifiedFilter(), None)
    rows = _by_uni(ds.rows)["Uni Delta"]
    assert len(rows) == 1
    row = rows[0]
    assert row["contract_number"] is None
    assert row["responsible"] == "Resp One; Resp Two"  # sorted aggregate
    assert row["workflow_status"] == "Stage 2"  # current instance stage
    assert row["health_score"] is None


def test_workflow_falls_back_to_program_status(fx):
    s, _, _ = fx
    ds = _fetch(s, UnifiedFilter(), None)
    rows = _by_uni(ds.rows)["Uni Epsilon"]
    assert len(rows) == 1
    assert rows[0]["workflow_status"] == "planned"
    assert rows[0]["responsible"] is None


def test_dates_are_typed_not_strings(fx):
    s, _, _ = fx
    ds = _fetch(s, UnifiedFilter(), None)
    for row in ds.rows:
        if row["license_signed"] is not None:
            assert isinstance(row["license_signed"], date)
        if row["license_expires"] is not None:
            assert isinstance(row["license_expires"], date)
        assert isinstance(row["health_score"], int) or row["health_score"] is None


def test_nulls_never_placeholders(fx):
    s, _, _ = fx
    ds = _fetch(s, UnifiedFilter(), None)
    for row in ds.rows:
        for value in row.values():
            assert value not in ("", "N/A", "-"), row


# ------------------------------------------------------------- row grain


def test_row_grain_no_cartesian_explosion(fx):
    s, _, _ = fx
    ds = _fetch(s, UnifiedFilter(), None)
    # 3 licenses + 3 license-less universities (Gamma, Delta, Epsilon).
    assert ds.total == 6
    assert ds.university_count == 5
    by_uni = _by_uni(ds.rows)
    # Alpha: 2 programs + 1 product-link + 1 responsible, but only 2 license rows.
    assert len(by_uni["Uni Alpha"]) == 2
    assert len(by_uni["Uni Beta"]) == 1


def test_deterministic_ordering(fx):
    s, _, _ = fx
    first = [(r["university"], r["contract_number"]) for r in _fetch(s, UnifiedFilter(), None).rows]
    second = [(r["university"], r["contract_number"]) for r in _fetch(s, UnifiedFilter(), None).rows]
    assert first == second
    assert [u for u, _ in first] == [
        "Uni Alpha", "Uni Alpha", "Uni Beta", "Uni Delta", "Uni Epsilon", "Uni Gamma",
    ]


# ------------------------------------------------------- column selection


def test_column_subset_only_requested_keys(fx):
    s, _, _ = fx
    ds = _fetch(s, UnifiedFilter(), ["university", "health_score"])
    assert ds.columns == ["university", "health_score"]
    for row in ds.rows:
        assert set(row.keys()) == {"university", "health_score"}
    by_uni = _by_uni(ds.rows)
    assert by_uni["Uni Alpha"][0]["health_score"] == 85
    assert by_uni["Uni Gamma"][0]["health_score"] is None


def test_unknown_column_rejected(fx):
    s, _, _ = fx
    with pytest.raises(UnknownReportColumnError):
        _fetch(s, UnifiedFilter(), ["university", "bogus"])


def test_duplicate_columns_deduped(fx):
    s, _, _ = fx
    ds = _fetch(s, UnifiedFilter(), ["university", "university", "health_score"])
    assert ds.columns == ["university", "health_score"]
    for row in ds.rows:
        assert set(row.keys()) == {"university", "health_score"}


def test_empty_columns_rejected(fx):
    s, _, _ = fx
    with pytest.raises(EmptyReportColumnsError):
        _fetch(s, UnifiedFilter(), [])


def test_optional_columns(fx):
    s, _, _ = fx
    ds = _fetch(s, UnifiedFilter(), ["university", "city", "current_stage"])
    assert ds.columns == ["university", "city", "current_stage"]
    by_uni = _by_uni(ds.rows)
    assert by_uni["Uni Alpha"][0]["current_stage"] == "Stage 2"
    assert by_uni["Uni Epsilon"][0]["current_stage"] is None


# ------------------------------------------------------- dynamic query


def test_minimal_columns_skip_heavy_joins():
    stmt = Dataset.build_query(UnifiedFilter(), ["university"], today=TODAY)
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True})).upper()
    assert "LICENSES" not in compiled
    assert "IT_PRODUCTS" not in compiled
    full = Dataset.build_query(UnifiedFilter(), None, today=TODAY)
    compiled_full = str(full.compile(compile_kwargs={"literal_binds": True})).upper()
    assert "LICENSES" in compiled_full


def test_filter_only_relation_without_output_column(fx):
    s, _, ids = fx
    ds = _fetch(s, UnifiedFilter(direction_ids=[ids["d1"]]), ["university"])
    assert ds.columns == ["university"]
    assert sorted(r["university"] for r in ds.rows) == ["Uni Alpha", "Uni Epsilon"]


def test_query_count_bounded(fx, select_counter):
    s, _, _ = fx
    select_counter["n"] = 0
    _fetch(s, UnifiedFilter(), None)
    assert select_counter["n"] == 2  # main SELECT + one batched responsibles query
    select_counter["n"] = 0
    _fetch(s, UnifiedFilter(), ["university", "health_score"])
    assert select_counter["n"] == 1  # no responsibles batch needed


# ------------------------------------------------------- unified filter dims


def test_filter_university_ids(fx):
    s, _, ids = fx
    # columns=["university"] needs no license join -> university grain (1 row).
    ds = _fetch(s, UnifiedFilter(university_ids=[ids["alpha"]]), ["university"])
    assert [r["university"] for r in ds.rows] == ["Uni Alpha"]
    assert ds.university_ids == {ids["alpha"]}
    # License-level columns switch to license grain (2 license rows).
    ds = _fetch(s, UnifiedFilter(university_ids=[ids["alpha"]]), None)
    assert len(ds.rows) == 2
    assert ds.university_ids == {ids["alpha"]}


def test_filter_direction_ids(fx):
    s, _, ids = fx
    ds = _fetch(s, UnifiedFilter(direction_ids=[ids["d2"]]), ["university"])
    assert sorted({r["university"] for r in ds.rows}) == ["Uni Beta"]


def test_filter_program_ids(fx):
    s, _, ids = fx
    ds = _fetch(s, UnifiedFilter(program_ids=[ids["p3"]]), ["university"])
    assert sorted({r["university"] for r in ds.rows}) == ["Uni Beta"]


def test_filter_product_ids(fx):
    s, _, ids = fx
    ds = _fetch(s, UnifiedFilter(product_ids=[ids["prod1"]]), ["university"])
    assert sorted({r["university"] for r in ds.rows}) == ["Uni Alpha", "Uni Delta"]


def test_filter_responsible_ids_no_duplicates(fx):
    s, _, ids = fx
    ds = _fetch(s, UnifiedFilter(responsible_ids=[ids["r1"]]), ["university"])
    # Delta has 2 responsibles incl. r1 -> still one fallback row.
    assert sorted({r["university"] for r in ds.rows}) == ["Uni Alpha", "Uni Delta"]


def test_filter_workflow_statuses(fx):
    s, _, _ = fx
    ds = _fetch(
        s, UnifiedFilter(workflow_statuses=[WorkflowStageStatus.COMPLETED]), ["university"]
    )
    assert sorted({r["university"] for r in ds.rows}) == ["Uni Alpha"]
    ds = _fetch(
        s, UnifiedFilter(workflow_statuses=[WorkflowStageStatus.SKIPPED]), ["university"]
    )
    assert sorted({r["university"] for r in ds.rows}) == ["Uni Delta"]
    ds = _fetch(
        s, UnifiedFilter(workflow_statuses=[WorkflowStageStatus.OVERDUE]), ["university"]
    )
    assert sorted({r["university"] for r in ds.rows}) == ["Uni Alpha"]


def test_filter_dates_on_created_at(fx):
    s, _, _ = fx
    ds = _fetch(
        s, UnifiedFilter(date_from=date(2026, 2, 1), date_to=date(2026, 6, 1)),
        ["university"],
    )
    assert sorted({r["university"] for r in ds.rows}) == [
        "Uni Beta", "Uni Delta", "Uni Epsilon",
    ]


def test_combined_dimensions_and(fx):
    s, _, ids = fx
    ds = _fetch(
        s,
        UnifiedFilter(direction_ids=[ids["d1"]], product_ids=[ids["prod1"]]),
        ["university"],
    )
    assert sorted({r["university"] for r in ds.rows}) == ["Uni Alpha"]


# ------------------------------------------------------- security + pins


def test_security_scope_confines_dataset(fx):
    s, _, ids = fx
    scoped = CurrentUser(
        id="scoped", roles={"user"}, university_ids=(str(ids["beta"]),)
    )
    ds = _fetch(
        s, UnifiedFilter(university_ids=[ids["alpha"], ids["beta"]]), None, user=scoped
    )
    assert ds.university_ids == {ids["beta"]}
    foreign = CurrentUser(
        id="scoped", roles={"user"}, university_ids=(str(ids["beta"]),)
    )
    ds = _fetch(s, UnifiedFilter(university_ids=[ids["alpha"]]), None, user=foreign)
    assert ds.total == 0


def test_dataset_matches_p1_and_analytics_university_sets(fx):
    s, _, ids = fx
    f = UnifiedFilter(direction_ids=[ids["d1"]], product_ids=[ids["prod1"], ids["prod2"]])
    ds = _fetch(s, f, ["university"])
    rows, total = UnifiedFilterService.paginate_universities(
        s, f, page=1, page_size=20, today=TODAY
    )
    p1_ids = {u.id for u in rows}
    assert total == len(p1_ids)
    assert ds.university_ids == p1_ids
    assert set(AnalyticsService.filtered_university_ids(s, f, today=TODAY)) == p1_ids


def test_health_fallback_does_not_reintroduce_snapshot_reads(fx):
    s, _, ids = fx
    ds = _fetch(s, UnifiedFilter(university_ids=[ids["gamma"]]), None)
    assert _by_uni(ds.rows)["Uni Gamma"][0]["health_score"] is None
    ds = _fetch(s, UnifiedFilter(university_ids=[ids["gamma"]]), None, health_fallback=True)
    assert _by_uni(ds.rows)["Uni Gamma"][0]["health_score"] is None
    # Snapshotted universities keep their snapshot values.
    ds = _fetch(
        s,
        UnifiedFilter(university_ids=[ids["alpha"], ids["beta"]]),
        ["university", "health_score"],
        health_fallback=True,
    )
    by_uni = _by_uni(ds.rows)
    assert by_uni["Uni Alpha"][0]["health_score"] == 85
    assert by_uni["Uni Beta"][0]["health_score"] == 60


def test_build_query_uses_shared_service_predicates(fx):
    s, _, ids = fx
    stmt = Dataset.build_query(
        UnifiedFilter(responsible_ids=[ids["r1"], ids["r2"]]), ["university"], today=TODAY
    )
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True})).upper()
    assert "EXISTS" in compiled
    outer = compiled.split("WHERE", 1)[0]
    assert "JOIN" not in outer
