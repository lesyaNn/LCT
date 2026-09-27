"""P4-01-01 PostgreSQL integration tests: FilterService on canonical PG16.

Deterministic fixture (reusable for P4-01-02/P4-12):

* Uni Alpha (2026-01-10): programs p1+p2 (both of direction d1), product
  prod1, responsible r1; workflow instance with one completed stage and one
  overdue pending current stage.
* Uni Beta (2026-05-20): program p3 (direction d2), product prod2,
  responsible r2; workflow instance with a future pending current stage.
* Uni Gamma (2026-08-01): no links, no workflow.
* Uni Delta (2026-03-15): product prod1, responsibles r1+r2; workflow
  instance with one skipped stage and a future pending current stage.

Covers §27-§30: every dimension, combined AND, within-dimension OR, no
duplicate rows, unknown UUIDs (-> 0 rows), security scope composition and
an EXPLAIN smoke check. Requires
``TEST_DATABASE_URL=postgresql+psycopg://...`` (skipped otherwise).
"""

import os
import uuid
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

import app.models  # noqa: F401 (register metadata)
from app.core.security import CurrentUser
from app.models.catalog import (
    ITDirection,
    ITProduct,
    ITProgram,
    Responsible,
    University,
    UniversityResponsible,
    Vendor,
)
from app.models.interactions import (
    InteractionNote,
    Meeting,
    UniversityProduct,
    UniversityProgram,
)
from app.models.workflow_instances import InstanceStage, WorkflowInstance
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate
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
        yield session, ids
    eng.dispose()


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
    s.add_all([d1, d2, p1, p2, p3, vendor, prod1, prod2, r1, r2,
               alpha, beta, gamma, delta])
    s.flush()
    s.add_all([
        UniversityProgram(university_id=alpha.id, program_id=p1.id),
        UniversityProgram(university_id=alpha.id, program_id=p2.id),
        UniversityProgram(university_id=beta.id, program_id=p3.id),
        UniversityProduct(university_id=alpha.id, product_id=prod1.id),
        UniversityProduct(university_id=beta.id, product_id=prod2.id),
        UniversityProduct(university_id=delta.id, product_id=prod1.id),
        UniversityResponsible(university_id=alpha.id, responsible_id=r1.id),
        UniversityResponsible(university_id=beta.id, responsible_id=r2.id),
        UniversityResponsible(university_id=delta.id, responsible_id=r1.id),
        UniversityResponsible(university_id=delta.id, responsible_id=r2.id),
    ])
    # One interaction per university, in the same month as its created_at, so
    # the date-filter tests keep selecting universities by month while
    # exercising the ТЗ INTERACTION period instead of ``created_at``.
    s.add_all([
        Meeting(id=uuid4(), university_id=u.id, meeting_type="online",
                subject=f"Meeting {n}", participants=[],
                meeting_at=at, created_by_keycloak_sub="t")
        for n, (u, at) in enumerate((
            (alpha, _utc(2026, 1, 20)),
            (beta, _utc(2026, 5, 25)),
            (gamma, _utc(2026, 8, 5)),
            (delta, _utc(2026, 3, 20)),
        ))
    ])
    # One note in a month no meeting covers, so the two interaction sources are
    # both exercised: Alpha gets a note in February.
    s.add(InteractionNote(
        id=uuid4(), university_id=alpha.id, author_keycloak_sub="t",
        content="February note", is_internal=True, created_at=_utc(2026, 2, 3),
    ))
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
    return {
        "d1": d1.id, "d2": d2.id,
        "p1": p1.id, "p2": p2.id, "p3": p3.id,
        "prod1": prod1.id, "prod2": prod2.id,
        "r1": r1.id, "r2": r2.id,
        "alpha": alpha.id, "beta": beta.id,
        "gamma": gamma.id, "delta": delta.id,
    }


def _names(session: Session, f: UnifiedFilter) -> list[str]:
    stmt = UnifiedFilterService.apply_to_universities(
        select(University), f, today=TODAY
    )
    return sorted(u.name for u in session.execute(stmt).scalars().all())


def _name_set(session: Session, f: UnifiedFilter) -> set[str]:
    return set(_names(session, f))


# ------------------------------------------------------------ university_ids


def test_university_ids_single(fx):
    s, ids = fx
    assert _names(s, UnifiedFilter(university_ids=[ids["alpha"]])) == ["Uni Alpha"]


def test_university_ids_multi(fx):
    s, ids = fx
    got = _name_set(
        s, UnifiedFilter(university_ids=[ids["alpha"], ids["beta"]])
    )
    assert got == {"Uni Alpha", "Uni Beta"}


def test_university_ids_unknown_uuid_returns_zero_rows(fx):
    s, _ = fx
    assert _names(s, UnifiedFilter(university_ids=[uuid.uuid4()])) == []


def test_university_ids_empty_returns_all(fx):
    s, _ = fx
    assert _name_set(s, UnifiedFilter()) == {
        "Uni Alpha", "Uni Beta", "Uni Gamma", "Uni Delta",
    }


# ------------------------------------------------------------ direction_ids


def test_direction_ids_single_no_duplicate_rows(fx):
    s, ids = fx
    rows = _names(s, UnifiedFilter(direction_ids=[ids["d1"]]))
    assert rows == ["Uni Alpha"]  # two matching programs -> still listed once


def test_direction_ids_multi_or(fx):
    s, ids = fx
    assert _name_set(
        s, UnifiedFilter(direction_ids=[ids["d1"], ids["d2"]])
    ) == {"Uni Alpha", "Uni Beta"}


def test_direction_ids_unknown_returns_zero_rows(fx):
    s, _ = fx
    assert _names(s, UnifiedFilter(direction_ids=[uuid.uuid4()])) == []


# --------------------------------------------------------------- program_ids


def test_program_ids_single(fx):
    s, ids = fx
    assert _names(s, UnifiedFilter(program_ids=[ids["p3"]])) == ["Uni Beta"]


def test_program_ids_multi_select_or(fx):
    s, ids = fx
    assert _name_set(
        s, UnifiedFilter(program_ids=[ids["p1"], ids["p3"]])
    ) == {"Uni Alpha", "Uni Beta"}
    # Two matching programs of one university -> one row.
    assert _names(s, UnifiedFilter(program_ids=[ids["p1"], ids["p2"]])) == [
        "Uni Alpha"
    ]


# --------------------------------------------------------------- product_ids


def test_product_ids(fx):
    s, ids = fx
    assert _name_set(
        s, UnifiedFilter(product_ids=[ids["prod1"]])
    ) == {"Uni Alpha", "Uni Delta"}
    assert _names(s, UnifiedFilter(product_ids=[ids["prod2"]])) == ["Uni Beta"]


# ----------------------------------------------------------- responsible_ids


def test_responsible_ids_no_duplicate_rows(fx):
    s, ids = fx
    assert _name_set(
        s, UnifiedFilter(responsible_ids=[ids["r1"]])
    ) == {"Uni Alpha", "Uni Delta"}
    rows = _names(s, UnifiedFilter(responsible_ids=[ids["r2"]]))
    assert rows == ["Uni Beta", "Uni Delta"]


# ---------------------------------------------------------- workflow_statuses


def test_workflow_completed(fx):
    s, _ = fx
    assert _names(
        s, UnifiedFilter(workflow_statuses=[WorkflowStageStatus.COMPLETED])
    ) == ["Uni Alpha"]


def test_workflow_pending(fx):
    s, _ = fx
    assert _name_set(
        s, UnifiedFilter(workflow_statuses=[WorkflowStageStatus.PENDING])
    ) == {"Uni Alpha", "Uni Beta", "Uni Delta"}


def test_workflow_skipped(fx):
    s, _ = fx
    assert _names(
        s, UnifiedFilter(workflow_statuses=[WorkflowStageStatus.SKIPPED])
    ) == ["Uni Delta"]


def test_workflow_current(fx):
    s, _ = fx
    assert _name_set(
        s, UnifiedFilter(workflow_statuses=[WorkflowStageStatus.CURRENT])
    ) == {"Uni Alpha", "Uni Beta", "Uni Delta"}


def test_workflow_overdue(fx):
    s, _ = fx
    assert _names(
        s, UnifiedFilter(workflow_statuses=[WorkflowStageStatus.OVERDUE])
    ) == ["Uni Alpha"]


def test_workflow_multi_status_or(fx):
    s, _ = fx
    assert _name_set(
        s,
        UnifiedFilter(
            workflow_statuses=[
                WorkflowStageStatus.COMPLETED,
                WorkflowStageStatus.SKIPPED,
            ]
        ),
    ) == {"Uni Alpha", "Uni Delta"}


def test_workflow_no_match_returns_zero_rows(fx):
    s, ids = fx
    # Gamma has no workflow instance at all.
    assert _names(
        s,
        UnifiedFilter(
            university_ids=[ids["gamma"]],
            workflow_statuses=[WorkflowStageStatus.PENDING],
        ),
    ) == []


# ------------------------------------------------------------------ combined


def test_combined_dimensions_and(fx):
    s, ids = fx
    assert _names(
        s,
        UnifiedFilter(direction_ids=[ids["d1"]], product_ids=[ids["prod1"]]),
    ) == ["Uni Alpha"]
    assert (
        _names(
            s,
            UnifiedFilter(
                direction_ids=[ids["d1"]], product_ids=[ids["prod2"]]
            ),
        )
        == []
    )


def test_combined_three_dimensions_and(fx):
    s, ids = fx
    assert _names(
        s,
        UnifiedFilter(
            university_ids=[ids["alpha"], ids["delta"]],
            product_ids=[ids["prod1"]],
            responsible_ids=[ids["r1"]],
        ),
    ) == ["Uni Alpha", "Uni Delta"]
    assert (
        _names(
            s,
            UnifiedFilter(
                university_ids=[ids["alpha"], ids["delta"]],
                product_ids=[ids["prod1"]],
                responsible_ids=[ids["r2"]],
            ),
        )
        == ["Uni Delta"]
    )


def test_within_dimension_or_between_dimensions_and(fx):
    s, ids = fx
    # (alpha OR beta) AND prod1 -> alpha only.
    assert _names(
        s,
        UnifiedFilter(
            university_ids=[ids["alpha"], ids["beta"]],
            product_ids=[ids["prod1"]],
        ),
    ) == ["Uni Alpha"]


# --------------------------------------------------------------------- dates


def test_date_range_on_interactions(fx):
    """ТЗ: the period bounds the interaction date, not the creation date."""
    s, _ = fx
    assert _name_set(
        s,
        UnifiedFilter(date_from=date(2026, 3, 1), date_to=date(2026, 6, 1)),
    ) == {"Uni Beta", "Uni Delta"}


def test_date_from_only(fx):
    s, _ = fx
    assert _name_set(s, UnifiedFilter(date_from=date(2026, 6, 1))) == {"Uni Gamma"}


def test_date_to_only(fx):
    s, _ = fx
    assert _name_set(s, UnifiedFilter(date_to=date(2026, 1, 31))) == {"Uni Alpha"}


def test_date_bounds_inclusive(fx):
    s, _ = fx
    # Delta's meeting is on 2026-03-20; a single-day range on that exact day
    # must match, proving both bounds are inclusive.
    assert _names(
        s,
        UnifiedFilter(date_from=date(2026, 3, 20), date_to=date(2026, 3, 20)),
    ) == ["Uni Delta"]
    # The same day without an interaction matches nobody.
    assert _names(
        s,
        UnifiedFilter(date_from=date(2026, 3, 15), date_to=date(2026, 3, 15)),
    ) == []


def test_period_matches_notes_when_there_is_no_meeting(fx):
    """``interaction_notes.created_at`` is an equally valid interaction."""
    s, _ = fx
    # Alpha has a January meeting AND a February note.
    assert _name_set(
        s, UnifiedFilter(date_from=date(2026, 2, 1), date_to=date(2026, 2, 28))
    ) == {"Uni Alpha"}


# ------------------------------------------------------------------ duplicates


def test_duplicate_filter_ids_single_row(fx):
    s, ids = fx
    f = UnifiedFilter(university_ids=[ids["alpha"], ids["alpha"]])
    assert f.university_ids == [ids["alpha"]]
    assert _names(s, f) == ["Uni Alpha"]


# ------------------------------------------------------- paginate adapter (P1)


def test_paginate_adapter_page_and_total(fx):
    s, _ = fx
    rows, total = UnifiedFilterService.paginate_universities(
        s, UnifiedFilter(), page=1, page_size=2, today=TODAY
    )
    assert total == 4
    assert [u.name for u in rows] == ["Uni Alpha", "Uni Beta"]
    rows2, total2 = UnifiedFilterService.paginate_universities(
        s, UnifiedFilter(), page=2, page_size=2, today=TODAY
    )
    assert total2 == 4
    assert [u.name for u in rows2] == ["Uni Delta", "Uni Gamma"]


def test_paginate_adapter_with_filter(fx):
    s, ids = fx
    rows, total = UnifiedFilterService.paginate_universities(
        s,
        UnifiedFilter(product_ids=[ids["prod1"]]),
        page=1,
        page_size=20,
        today=TODAY,
    )
    assert total == 2
    assert [u.name for u in rows] == ["Uni Alpha", "Uni Delta"]


# ------------------------------------------------------------------ security


def test_security_scope_cannot_widen_filter(fx):
    s, ids = fx
    scoped = CurrentUser(
        id="scoped", roles={"user"}, university_ids=(str(ids["beta"]),)
    )
    stmt = UnifiedFilterService.apply_to_universities(
        select(University),
        UnifiedFilter(university_ids=[ids["alpha"], ids["beta"]]),
        today=TODAY,
    )
    stmt = UnifiedFilterService.apply_security_scope(stmt, scoped)
    assert sorted(u.name for u in s.execute(stmt).scalars().all()) == ["Uni Beta"]


def test_security_scope_foreign_only_filter_returns_zero(fx):
    s, ids = fx
    scoped = CurrentUser(
        id="scoped", roles={"user"}, university_ids=(str(ids["beta"]),)
    )
    stmt = UnifiedFilterService.apply_to_universities(
        select(University),
        UnifiedFilter(university_ids=[ids["alpha"]]),
        today=TODAY,
    )
    stmt = UnifiedFilterService.apply_security_scope(stmt, scoped)
    assert list(s.execute(stmt).scalars().all()) == []


def test_security_scope_admin_sees_all(fx):
    s, ids = fx
    admin = CurrentUser(id="admin", roles={"admin"})
    stmt = UnifiedFilterService.apply_to_universities(
        select(University),
        UnifiedFilter(university_ids=[ids["alpha"]]),
        today=TODAY,
    )
    stmt = UnifiedFilterService.apply_security_scope(stmt, admin)
    assert [u.name for u in s.execute(stmt).scalars().all()] == ["Uni Alpha"]


# ------------------------------------------------------------------- explain


def test_explain_combined_filter_executes(fx):
    s, ids = fx
    stmt = UnifiedFilterService.apply_to_universities(
        select(University),
        UnifiedFilter(
            direction_ids=[ids["d1"]],
            responsible_ids=[ids["r1"], ids["r2"]],
            workflow_statuses=[WorkflowStageStatus.PENDING],
        ),
        today=TODAY,
    )
    compiled = stmt.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    plan = s.execute(text(f"EXPLAIN {compiled}")).scalars().all()
    assert plan, "EXPLAIN must return a plan"
    assert any("universities" in line.lower() for line in plan)
    rows = s.execute(stmt).scalars().all()
    assert [u.name for u in rows] == ["Uni Alpha"]


# ------------------------------------------------------------ unknown uuids


def test_unknown_uuids_every_dimension_zero_rows(fx):
    s, _ = fx
    ghost = uuid.uuid4()
    assert (
        _names(
            s,
            UnifiedFilter(
                university_ids=[ghost],
                direction_ids=[ghost],
                program_ids=[ghost],
                product_ids=[ghost],
                responsible_ids=[ghost],
            ),
        )
        == []
    )
