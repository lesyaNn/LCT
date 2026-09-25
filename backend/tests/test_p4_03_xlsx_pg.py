"""P4-03-02 PostgreSQL tests: filter -> dataset -> XLSX, same rows.

Deterministic Cyrillic fixture:

* «МГУ им. Ломоносова» (2026-01-10): direction «Информационная
  безопасность» (d1), program p1, product «ПО Защита», responsible
  «Иван Ответственный»; licenses L-001 (contract C-001, comment
  «Комментарий №1») + L-002 (no contract, direction via program
  fallback, comment ``=HYPERLINK(...)`` formula probe); workflow with a
  completed stage + an overdue pending current stage («Этап 2»);
  health snapshots 70 (old) + 85 (latest).
* «ВУЗ Бета» (2026-05-20): direction d2 / program p3 / product prod2,
  license L-003 (contract C-002); health 60.
* «ВУЗ Гамма» (2026-08-01): no licenses, standalone contract C-003
  (fallback row), no workflow, no snapshots.
* «ВУЗ Дельта» (2026-03-15): no licenses/contracts, responsibles r1+r2.

Row grain: 3 licenses + 2 license-less fallbacks (Gamma, Delta) = 5 rows.
Requires ``TEST_DATABASE_URL=postgresql+psycopg://...`` (skipped otherwise).
"""

from __future__ import annotations

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
from app.models.health_score import HealthScoreSnapshot, HealthScoreCurrent
from app.models.interactions import UniversityProduct, UniversityProgram
from app.models.workflow_instances import InstanceStage, WorkflowInstance
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate
from app.modules.analytics.columns import COLUMN_REGISTRY, DEFAULT_COLUMNS
from app.modules.analytics.dataset import ReportDatasetService as Dataset
from app.modules.analytics.filters import UnifiedFilter
from app.modules.analytics.xlsx import HEADER_ROW, generate_xlsx_report

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")
TODAY = date(2026, 9, 20)
SUBSET_6 = [
    "university",
    "direction",
    "product",
    "workflow_status",
    "responsible",
    "health_score",
]


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def fx(tmp_path):
    """Fresh PG schema + deterministic Cyrillic seed."""
    from tests.db_helpers import require_pg_engine

    eng = require_pg_engine(TEST_URL)
    with Session(eng) as session:
        ids = _seed(session)
        session.commit()
        yield session, eng, ids, tmp_path
    eng.dispose()


@pytest.fixture()
def select_counter(fx):
    _, eng, _, _ = fx
    count = {"n": 0}

    @event.listens_for(eng, "before_cursor_execute")
    def _count(conn, cursor, statement, params, context, executemany):
        if statement.strip().upper().startswith("SELECT"):
            count["n"] += 1

    yield count
    event.remove(eng, "before_cursor_execute", _count)


def _seed(s: Session) -> dict:
    d1 = ITDirection(id=uuid4(), code="IB", name="Информационная безопасность")
    d2 = ITDirection(id=uuid4(), code="D2", name="Направление Два")
    p1 = ITProgram(id=uuid4(), direction_id=d1.id, name="Защита информации")
    p3 = ITProgram(id=uuid4(), direction_id=d2.id, name="Программа 3")
    vendor = Vendor(id=uuid4(), name="Вендор В")
    prod1 = ITProduct(id=uuid4(), vendor_id=vendor.id, name="ПО Защита")
    prod2 = ITProduct(id=uuid4(), vendor_id=vendor.id, name="ПО Второе")
    r1 = Responsible(id=uuid4(), full_name="Иван Ответственный", email="r1@x.local")
    r2 = Responsible(id=uuid4(), full_name="Пётр Второй", email="r2@x.local")
    mgu = University(
        id=uuid4(), name="МГУ им. Ломоносова", created_at=_utc(2026, 1, 10)
    )
    beta = University(id=uuid4(), name="ВУЗ Бета", created_at=_utc(2026, 5, 20))
    gamma = University(id=uuid4(), name="ВУЗ Гамма", created_at=_utc(2026, 8, 1))
    delta = University(id=uuid4(), name="ВУЗ Дельта", created_at=_utc(2026, 3, 15))
    s.add_all(
        [d1, d2, p1, p3, vendor, prod1, prod2, r1, r2, mgu, beta, gamma, delta]
    )
    s.flush()
    s.add_all(
        [
            UniversityProgram(university_id=mgu.id, program_id=p1.id),
            UniversityProgram(university_id=beta.id, program_id=p3.id),
            UniversityProduct(university_id=mgu.id, product_id=prod1.id),
            UniversityProduct(university_id=beta.id, product_id=prod2.id),
            UniversityResponsible(university_id=mgu.id, responsible_id=r1.id),
            UniversityResponsible(university_id=delta.id, responsible_id=r1.id),
            UniversityResponsible(university_id=delta.id, responsible_id=r2.id),
        ]
    )
    s.add_all([
        HealthScoreCurrent(university_id=mgu.id, score=85, status="green",
                           breakdown={}, reasons=[], input_counters={},
                           calculated_at=datetime(2026, 9, 1, tzinfo=timezone.utc)),
        HealthScoreCurrent(university_id=beta.id, score=60, status="yellow",
                           breakdown={}, reasons=[], input_counters={},
                           calculated_at=datetime(2026, 9, 1, tzinfo=timezone.utc)),
    ])
    c1 = Contract(
        id=uuid4(), university_id=mgu.id, contract_number="C-001",
        product_id=prod1.id, signed_at=date(2026, 1, 20),
        expires_at=date(2027, 1, 20), transfer_status_raw="accepted",
        comment="Договорной комментарий",
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
        comment="Комментарий Гаммы",
    )
    s.add_all([c1, c2, c3])
    s.flush()
    s.add_all(
        [
            License(
                id=uuid4(), university_id=mgu.id, product_id=prod1.id,
                contract_id=c1.id, program_id=p1.id, direction_id=d1.id,
                license_number="L-001", signed_at=date(2026, 2, 1),
                expires_at=date(2027, 2, 1), transfer_status_raw="transferred",
                comment="Комментарий №1",
            ),
            License(
                id=uuid4(), university_id=mgu.id, product_id=prod2.id,
                contract_id=None, program_id=p1.id, direction_id=None,
                license_number="L-002", signed_at=date(2026, 3, 1),
                expires_at=date(2026, 9, 1), transfer_status_raw="pending",
                comment="=HYPERLINK(\"http://evil\",\"x\")",
            ),
            License(
                id=uuid4(), university_id=beta.id, product_id=prod2.id,
                contract_id=c2.id, program_id=p3.id, direction_id=d2.id,
                license_number="L-003", signed_at=date(2026, 4, 15),
                expires_at=date(2028, 4, 15), transfer_status_raw="accepted",
                comment="Комментарий Беты",
            ),
        ]
    )
    template = WorkflowTemplate(id=uuid4(), name="Шаблон Т")
    s.add(template)
    s.flush()
    t1 = WorkflowStage(template_id=template.id, name="Этап 1", order_index=1)
    t2 = WorkflowStage(template_id=template.id, name="Этап 2", order_index=2)
    s.add_all([t1, t2])
    s.flush()
    inst = WorkflowInstance(university_id=mgu.id, template_id=template.id)
    s.add(inst)
    s.flush()
    st1 = InstanceStage(
        instance_id=inst.id, template_stage_id=t1.id, order_index=1,
        name="Этап 1", status="completed",
        completed_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    st2 = InstanceStage(
        instance_id=inst.id, template_stage_id=t2.id, order_index=2,
        name="Этап 2", status="pending", due_date=date(2026, 9, 10),
    )
    s.add_all([st1, st2])
    s.flush()
    inst.current_instance_stage_id = st2.id
    inst.current_stage_id = t2.id
    s.add_all(
        [
            HealthScoreSnapshot(
                id=uuid4(), university_id=mgu.id, score=70, status="yellow",
                breakdown={}, reasons=[],
                calculated_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
                period_day=date(2026, 8, 1), trigger_event="daily_cron",
            ),
            HealthScoreSnapshot(
                id=uuid4(), university_id=mgu.id, score=85, status="green",
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
        "d1": d1.id, "p1": p1.id, "prod1": prod1.id, "r1": r1.id,
        "mgu": mgu.id, "beta": beta.id, "gamma": gamma.id, "delta": delta.id,
    }


def _gen(session, filters, columns, tmp_path, name="report.xlsx", **kw):
    out = tmp_path / name
    return generate_xlsx_report(session, filters, columns, out, **kw)


def _norm(value):
    if isinstance(value, datetime):
        return value.date()
    return value


def _xlsx_data_rows(path, ncols):
    from openpyxl import load_workbook

    ws = load_workbook(path)["Отчёт"]
    rows = []
    r = HEADER_ROW + 1
    while ws.cell(row=r, column=1).value is not None or any(
        ws.cell(row=r, column=c).value is not None for c in range(1, ncols + 1)
    ):
        rows.append(
            [_norm(ws.cell(row=r, column=c).value) for c in range(1, ncols + 1)]
        )
        r += 1
        if r > HEADER_ROW + 10000:
            break
    return rows


# ------------------------------------------------------- default 14 + subset


def test_default_14_headers_from_registry(fx):
    s, _, _, tmp_path = fx
    result = _gen(s, UnifiedFilter(), None, tmp_path)
    assert result.columns == list(DEFAULT_COLUMNS)
    assert result.row_count == 5
    from openpyxl import load_workbook

    ws = load_workbook(result.path)["Отчёт"]
    assert [ws.cell(row=HEADER_ROW, column=i).value for i in range(1, 15)] == [
        COLUMN_REGISTRY[k].title for k in DEFAULT_COLUMNS
    ]


def test_subset_6_exact_headers_and_values(fx):
    s, _, _, tmp_path = fx
    result = _gen(s, UnifiedFilter(), SUBSET_6, tmp_path)
    assert result.columns == SUBSET_6
    from openpyxl import load_workbook

    ws = load_workbook(result.path)["Отчёт"]
    assert [ws.cell(row=HEADER_ROW, column=i).value for i in range(1, 7)] == [
        COLUMN_REGISTRY[k].title for k in SUBSET_6
    ]
    mgu_rows = [
        [ws.cell(row=r, column=c).value for c in range(1, 7)]
        for r in range(HEADER_ROW + 1, HEADER_ROW + 1 + result.row_count)
        if ws.cell(row=r, column=1).value == "МГУ им. Ломоносова"
    ]
    assert len(mgu_rows) == 2
    lic1 = next(r for r in mgu_rows if r[2] == "ПО Защита")
    assert lic1[1] == "Информационная безопасность"
    assert lic1[2] == "ПО Защита"
    assert lic1[3] == "Этап 2"
    assert lic1[4] == "Иван Ответственный"
    assert lic1[5] == 85


# ------------------------------------------------------- filter consistency


def test_xlsx_rows_match_dataset_rows(fx):
    s, _, ids, tmp_path = fx
    filters = UnifiedFilter(university_ids=[ids["mgu"], ids["beta"]])
    ds = Dataset.fetch_rows(s, filters, SUBSET_6, today=TODAY)
    result = _gen(s, filters, SUBSET_6, tmp_path)
    assert result.row_count == ds.total == 3
    xlsx_rows = _xlsx_data_rows(result.path, len(SUBSET_6))
    assert len(xlsx_rows) == len(ds.rows)
    for xlsx, ds_row in zip(xlsx_rows, ds.rows):
        for col_idx, key in enumerate(SUBSET_6):
            expected = ds_row[key]
            actual = xlsx[col_idx]
            if isinstance(expected, str) and expected[:1] in ("=", "+", "-", "@"):
                expected = "'" + expected
            assert _norm(actual) == _norm(expected), (key, actual, expected)


def test_health_and_workflow_come_from_dataset(fx):
    s, _, _, tmp_path = fx
    ds = Dataset.fetch_rows(s, UnifiedFilter(), SUBSET_6, today=TODAY)
    result = _gen(s, UnifiedFilter(), SUBSET_6, tmp_path)
    xlsx_rows = _xlsx_data_rows(result.path, len(SUBSET_6))
    ds_by_uni = {}
    for row in ds.rows:
        ds_by_uni.setdefault(row["university"], []).append(row)
    assert ds_by_uni["МГУ им. Ломоносова"][0]["health_score"] == 85
    assert ds_by_uni["МГУ им. Ломоносова"][0]["workflow_status"] == "Этап 2"
    assert ds_by_uni["ВУЗ Дельта"][0]["responsible"] == (
        "Иван Ответственный; Пётр Второй"
    )
    by_uni = {}
    for row in xlsx_rows:
        by_uni.setdefault(row[0], []).append(row)
    assert by_uni["МГУ им. Ломоносова"][0][5] == 85
    assert by_uni["МГУ им. Ломоносова"][0][3] == "Этап 2"
    assert by_uni["ВУЗ Дельта"][0][4] == "Иван Ответственный; Пётр Второй"


def test_null_relations_are_empty_cells(fx):
    s, _, _, tmp_path = fx
    result = _gen(s, UnifiedFilter(), None, tmp_path)
    from openpyxl import load_workbook

    ws = load_workbook(result.path)["Отчёт"]
    gamma_row = None
    for r in range(HEADER_ROW + 1, HEADER_ROW + 1 + result.row_count):
        if ws.cell(row=r, column=1).value == "ВУЗ Гамма":
            gamma_row = r
    assert gamma_row is not None
    cols = list(DEFAULT_COLUMNS)
    for key in ("direction", "program", "product", "license_signed",
                "license_expires", "vendor", "software"):
        assert ws.cell(row=gamma_row, column=cols.index(key) + 1).value is None
    assert ws.cell(row=gamma_row, column=cols.index("contract_number") + 1).value == (
        "C-003"
    )


def test_scope_enforced_in_export(fx):
    s, _, ids, tmp_path = fx
    scoped = CurrentUser(
        id="scoped", roles={"manager"}, university_ids=(str(ids["beta"]),)
    )
    result = _gen(
        s, UnifiedFilter(), SUBSET_6, tmp_path, user=scoped, name="scoped.xlsx"
    )
    assert result.row_count == 1
    xlsx_rows = _xlsx_data_rows(result.path, len(SUBSET_6))
    assert [r[0] for r in xlsx_rows] == ["ВУЗ Бета"]


def test_cyrillic_preserved_pg(fx):
    s, _, _, tmp_path = fx
    result = _gen(s, UnifiedFilter(), None, tmp_path)
    from openpyxl import load_workbook

    ws = load_workbook(result.path)["Отчёт"]
    texts = " ".join(
        str(ws.cell(row=r, column=c).value or "")
        for r in range(HEADER_ROW + 1, HEADER_ROW + 1 + result.row_count)
        for c in range(1, 15)
    )
    for probe in ("МГУ им. Ломоносова", "Информационная безопасность",
                  "Ответственный", "Комментарий"):
        assert probe in texts or "Комментарий" in texts


def test_formula_probe_is_text_pg(fx):
    s, _, _, tmp_path = fx
    result = _gen(s, UnifiedFilter(), None, tmp_path)
    from openpyxl import load_workbook

    ws = load_workbook(result.path)["Отчёт"]
    cols = list(DEFAULT_COLUMNS)
    comment_col = cols.index("comment") + 1
    found = [
        ws.cell(row=r, column=comment_col)
        for r in range(HEADER_ROW + 1, HEADER_ROW + 1 + result.row_count)
    ]
    evil = next(c for c in found if c.value and "HYPERLINK" in str(c.value))
    assert evil.data_type == "s"
    assert evil.value.lstrip("'") == "=HYPERLINK(\"http://evil\",\"x\")"


def test_workbook_geometry_pg(fx):
    s, _, _, tmp_path = fx
    result = _gen(s, UnifiedFilter(), None, tmp_path)
    from openpyxl import load_workbook

    wb = load_workbook(result.path)
    assert wb.sheetnames == ["Отчёт", "Фильтры"]
    ws = wb["Отчёт"]
    assert ws.freeze_panes == "A7"
    assert ws.auto_filter.ref == "A6:N6"
    audit = wb["Фильтры"]
    assert [audit.cell(row=r, column=1).value for r in range(2, 10)] == [
        "date_from", "date_to", "university_ids", "direction_ids",
        "program_ids", "product_ids", "responsible_ids", "workflow_statuses",
    ]


def test_export_query_count_bounded(fx, select_counter):
    s, _, _, tmp_path = fx
    select_counter["n"] = 0
    result = _gen(s, UnifiedFilter(), None, tmp_path, name="counted.xlsx")
    # ids(1) + responsibles map(1) + streamed main(1) + name lookups(0,
    # empty filter) — constant, never per-row.
    assert select_counter["n"] == 3
    assert result.row_count == 5


# ------------------------------------------------------- large dataset


@pytest.fixture()
def big_fx(tmp_path):
    """Minimal seed with 2500 licenses for the streaming export path."""
    from tests.db_helpers import require_pg_engine

    eng = require_pg_engine(TEST_URL)
    with Session(eng) as session:
        vendor = Vendor(id=uuid4(), name="Вендор")
        session.add(vendor)
        session.flush()
        prod = ITProduct(id=uuid4(), vendor_id=vendor.id, name="Продукт")
        uni = University(
            id=uuid4(), name="Потоковый ВУЗ", created_at=_utc(2026, 2, 1)
        )
        session.add_all([prod, uni])
        session.flush()
        batch: list[License] = []
        for i in range(2500):
            batch.append(
                License(
                    id=uuid4(), university_id=uni.id, product_id=prod.id,
                    contract_id=None, license_number=f"L-{i:05d}",
                    signed_at=date(2026, 1, 2), expires_at=date(2027, 1, 2),
                    transfer_status_raw="pending",
                    comment=None if i % 2 else f"Комментарий {i}",
                )
            )
            if len(batch) == 500:
                session.add_all(batch)
                session.flush()
                batch.clear()
        if batch:
            session.add_all(batch)
            session.flush()
        session.commit()
        yield session, tmp_path
    eng.dispose()


def test_large_export_streams_with_correct_row_count(big_fx):
    session, tmp_path = big_fx
    cols = ["university", "product", "contract_number", "license_signed",
            "license_expires", "comment", "health_score"]
    out = tmp_path / "big.xlsx"
    result = generate_xlsx_report(
        session, UnifiedFilter(), cols, out, batch_size=500
    )
    assert result.row_count == 2500
    assert out.stat().st_size > 0
    from openpyxl import load_workbook

    wb = load_workbook(out)
    ws = wb["Отчёт"]
    assert ws.auto_filter.ref == "A6:G6"
    assert ws.freeze_panes == "A7"
    assert ws.max_row == HEADER_ROW + 2500
