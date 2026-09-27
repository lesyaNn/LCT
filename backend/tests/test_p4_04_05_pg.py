"""P4-04 / P4-05 PostgreSQL tests: filter -> dataset -> PDF/JSON + cross-format.

Deterministic Cyrillic fixture (same grain as the P4-03-02 PG suite):

* «МГУ им. Ломоносова» (2026-01-10): 2 licenses (L-001 with contract C-001
  + comment «Комментарий №1»; L-002 without contract, formula probe),
  workflow «Этап 2», health snapshots 70 (old) + 85 (latest);
* «ВУЗ Бета» (2026-05-20): license L-003 (contract C-002), health 60;
* «ВУЗ Гамма» (2026-08-01): no licenses, standalone contract C-003
  (fallback row), no workflow, no snapshots;
* «ВУЗ Дельта» (2026-03-15): no licenses/contracts, responsibles r1+r2.

Row grain: 3 licenses + 2 license-less fallbacks = 5 rows.
Requires ``TEST_DATABASE_URL=postgresql+psycopg://...`` (skipped otherwise).
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
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
from app.models.interactions import (
    InteractionNote,
    Meeting,
    UniversityProduct,
    UniversityProgram,
)
from app.models.workflow_instances import InstanceStage, WorkflowInstance
from app.models.workflow_templates import WorkflowStage, WorkflowTemplate
from app.modules.analytics.columns import DEFAULT_COLUMNS
from app.modules.analytics.dataset import ReportDatasetService as Dataset
from app.modules.analytics.filters import UnifiedFilter
from app.modules.analytics.json_export import generate_json_report
from app.modules.analytics.pdf import ReportKpi, generate_pdf_report
from app.modules.analytics.xlsx import HEADER_ROW, generate_xlsx_report
from tests.test_p4_04_pdf_unit import _nospace, extract_pdf_text

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")
TODAY = date(2026, 9, 20)
SUBSET_6 = [
    "university",
    "direction",
    "product",
    "workflow_status",
    "responsible",
    "workflow_progress",
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
    mgu = University(id=uuid4(), name="МГУ им. Ломоносова", created_at=_utc(2026, 1, 10))
    beta = University(id=uuid4(), name="ВУЗ Бета", created_at=_utc(2026, 5, 20))
    gamma = University(id=uuid4(), name="ВУЗ Гамма", created_at=_utc(2026, 8, 1))
    delta = University(id=uuid4(), name="ВУЗ Дельта", created_at=_utc(2026, 3, 15))
    s.add_all([d1, d2, p1, p3, vendor, prod1, prod2, r1, r2, mgu, beta, gamma, delta])
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
    c1 = Contract(
        id=uuid4(),
        university_id=mgu.id,
        contract_number="C-001",
        product_id=prod1.id,
        signed_at=date(2026, 1, 20),
        expires_at=date(2027, 1, 20),
        transfer_status_raw="accepted",
        comment="Договорной комментарий",
    )
    c2 = Contract(
        id=uuid4(),
        university_id=beta.id,
        contract_number="C-002",
        product_id=prod2.id,
        signed_at=date(2026, 4, 1),
        expires_at=date(2028, 4, 1),
        transfer_status_raw="transferred",
        comment=None,
    )
    c3 = Contract(
        id=uuid4(),
        university_id=gamma.id,
        contract_number="C-003",
        product_id=None,
        signed_at=date(2026, 7, 1),
        expires_at=date(2027, 7, 1),
        transfer_status_raw="pending",
        comment="Комментарий Гаммы",
    )
    s.add_all([c1, c2, c3])
    s.flush()
    s.add_all(
        [
            License(
                id=uuid4(),
                university_id=mgu.id,
                product_id=prod1.id,
                contract_id=c1.id,
                program_id=p1.id,
                direction_id=d1.id,
                license_number="L-001",
                signed_at=date(2026, 2, 1),
                expires_at=date(2027, 2, 1),
                transfer_status_raw="transferred",
                comment="Комментарий №1",
            ),
            License(
                id=uuid4(),
                university_id=mgu.id,
                product_id=prod2.id,
                contract_id=None,
                program_id=p1.id,
                direction_id=None,
                license_number="L-002",
                signed_at=date(2026, 3, 1),
                expires_at=date(2026, 9, 1),
                transfer_status_raw="pending",
                comment='=HYPERLINK("http://evil","x")',
            ),
            License(
                id=uuid4(),
                university_id=beta.id,
                product_id=prod2.id,
                contract_id=c2.id,
                program_id=p3.id,
                direction_id=d2.id,
                license_number="L-003",
                signed_at=date(2026, 4, 15),
                expires_at=date(2028, 4, 15),
                transfer_status_raw="accepted",
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
        instance_id=inst.id,
        template_stage_id=t1.id,
        order_index=1,
        name="Этап 1",
        status="completed",
        completed_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    st2 = InstanceStage(
        instance_id=inst.id,
        template_stage_id=t2.id,
        order_index=2,
        name="Этап 2",
        status="pending",
        due_date=date(2026, 9, 10),
    )
    s.add_all([st1, st2])
    s.flush()
    inst.current_instance_stage_id = st2.id
    inst.current_stage_id = t2.id
    # Бета gets its own fully-completed instance, so `workflow_progress`
    # has two different real values (МГУ 50%, Бета 100%) to aggregate.
    inst_beta = WorkflowInstance(university_id=beta.id, template_id=template.id)
    s.add(inst_beta)
    s.flush()
    st_beta = InstanceStage(
        instance_id=inst_beta.id,
        template_stage_id=t1.id,
        order_index=1,
        name="Этап 1",
        status="completed",
        completed_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )
    s.add(st_beta)
    s.flush()
    inst_beta.current_instance_stage_id = None
    # Every seeded university gets an interaction, because the ТЗ period
    # filters on the interaction date (meetings / interaction notes), not on
    # the university creation date. A university without any interaction is
    # therefore excluded as soon as a period is set — covered explicitly by
    # test_period_filter_follows_interactions_not_creation_date.
    s.add_all([
        Meeting(
            id=uuid4(),
            university_id=u.id,
            meeting_type="online",
            subject=f"Встреча {n}",
            participants=[],
            meeting_at=_utc(2026, 9, 5),
            created_by_keycloak_sub="tester",
        )
        for n, u in enumerate((mgu, beta, gamma, delta))
    ])
    s.add(InteractionNote(
        id=uuid4(),
        university_id=mgu.id,
        author_keycloak_sub="tester",
        content="Заметка о встрече",
        is_internal=True,
    ))
    s.flush()
    return {"mgu": mgu.id, "beta": beta.id, "gamma": gamma.id, "delta": delta.id}


# ------------------------------------------------------- PDF over PG dataset


def test_pdf_rows_match_dataset_rows(fx):
    s, _, ids, tmp_path = fx
    filters = UnifiedFilter(university_ids=[ids["mgu"], ids["beta"]])
    ds = Dataset.fetch_rows(s, filters, SUBSET_6, today=TODAY)
    assert ds.total == 3  # 2 МГУ licenses + 1 Бета license
    result = generate_pdf_report(s, filters, SUBSET_6, tmp_path / "r.pdf")
    assert result.row_count == ds.total
    assert result.columns == SUBSET_6
    assert result.path.stat().st_size > 0
    text = _nospace(extract_pdf_text(result.path.read_bytes()))
    assert _nospace("МГУ им. Ломоносова") in text
    assert _nospace("ВУЗ Бета") in text
    assert _nospace("Нет данных для построения графика") not in text


def test_pdf_kpi_and_charts_from_pg_dataset(fx):
    s, _, _, tmp_path = fx
    # The default column set is the ТЗ set and does NOT include the progress
    # column, so a KPI that reports progress has to select it explicitly.
    cols = [*DEFAULT_COLUMNS, "workflow_progress"]
    ds = Dataset.fetch_rows(s, UnifiedFilter(), cols, today=TODAY)
    assert ds.total == 5
    kpi = ReportKpi()
    for row in ds.rows:
        kpi.add_row(row)
    assert kpi.row_count == 5
    assert kpi.university_count == 4
    # Row-grain mean over the 3 rows that carry a progress value:
    # МГУ 1/2 stages (50%) x2 rows + Бета 1/1 (100%) -> 66.7.
    assert kpi.avg_workflow_progress == pytest.approx(66.7, abs=0.05)
    result = generate_pdf_report(s, UnifiedFilter(), cols, tmp_path / "full.pdf")
    assert result.row_count == 5
    assert result.columns == cols
    text = _nospace(extract_pdf_text(result.path.read_bytes()))
    assert _nospace("Количество ВУЗов: 4") in text
    assert _nospace("Средний прогресс workflow, %: 66.7") in text
    assert _nospace("Зелёный") in text


def test_pdf_empty_filter_result_still_valid(fx):
    s, _, _, tmp_path = fx
    filters = UnifiedFilter(date_from=date(2020, 1, 1), date_to=date(2020, 1, 2))
    ds = Dataset.fetch_rows(s, filters, SUBSET_6, today=TODAY)
    assert ds.total == 0
    result = generate_pdf_report(s, filters, SUBSET_6, tmp_path / "empty.pdf")
    assert result.row_count == 0
    data = result.path.read_bytes()
    assert data[:5] == b"%PDF-"
    text = _nospace(extract_pdf_text(data))
    assert _nospace("Нет данных для построения графика") in text


def test_pdf_scoped_user_matches_dataset_scope(fx):
    s, _, ids, tmp_path = fx
    user = CurrentUser(id="scoped-1", roles={"manager"}, university_ids=(str(ids["beta"]),))
    filters = UnifiedFilter()
    ds = Dataset.fetch_rows(s, filters, SUBSET_6, user=user, today=TODAY)
    assert ds.total == 1
    assert ds.university_ids == frozenset({ids["beta"]})
    result = generate_pdf_report(s, filters, SUBSET_6, tmp_path / "scoped.pdf", user=user)
    assert result.row_count == ds.total
    text = _nospace(extract_pdf_text(result.path.read_bytes()))
    assert _nospace("ВУЗ Бета") in text
    assert _nospace("МГУ им. Ломоносова") not in text


# ------------------------------------------------------- JSON over PG dataset


def test_json_default_columns_and_unicode(fx):
    s, _, _, tmp_path = fx
    # Two exports: the ТЗ default set, and the extended set this test inspects
    # for contract/license types and fallback rows.
    ds = Dataset.fetch_rows(s, UnifiedFilter(), None, today=TODAY)
    generate_json_report(s, UnifiedFilter(), None, tmp_path / "default.json")
    default_doc = json.loads((tmp_path / "default.json").read_text(encoding="utf-8"))
    assert [entry["key"] for entry in default_doc["columns"]] == list(DEFAULT_COLUMNS)
    assert default_doc["totals"]["row_count"] == 5

    extended = [*DEFAULT_COLUMNS, "contract_number", "license_signed",
                "license_expires", "comment"]
    result = generate_json_report(s, UnifiedFilter(), extended, tmp_path / "r.json")
    assert result.row_count == ds.total == 5
    doc = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert all(entry["title"] for entry in doc["columns"])
    assert doc["totals"]["row_count"] == 5
    assert len(doc["rows"]) == 5
    lic1 = next(i for i in doc["rows"] if i.get("contract_number") == "C-001")
    assert lic1["university"] == "МГУ им. Ломоносова"
    assert lic1["product"] == "ПО Защита"
    assert lic1["contract_number"] == "C-001"
    assert lic1["license_signed"] == "2026-02-01"
    assert lic1["license_expires"] == "2027-02-01"
    assert lic1["comment"] == "Комментарий №1"
    gamma = next(i for i in doc["rows"] if i["university"] == "ВУЗ Гамма")
    assert gamma["direction"] is None
    assert gamma["product"] is None
    assert gamma["contract_number"] == "C-003"  # fallback row
    raw = (tmp_path / "r.json").read_bytes().decode("utf-8")
    assert "МГУ им. Ломоносова" in raw


def test_json_items_equal_dataset_rows(fx):
    s, _, ids, tmp_path = fx
    filters = UnifiedFilter(university_ids=[ids["mgu"], ids["beta"]])
    ds = Dataset.fetch_rows(s, filters, SUBSET_6, today=TODAY)
    generate_json_report(s, filters, SUBSET_6, tmp_path / "s.json")
    doc = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
    assert doc["rows"] == ds.rows  # SUBSET_6 values are str/int/None: identical
    assert doc["totals"]["row_count"] == ds.total == 3


def test_json_scoped_user_matches_dataset_scope(fx):
    s, _, ids, tmp_path = fx
    user = CurrentUser(id="scoped-1", roles={"manager"}, university_ids=(str(ids["gamma"]),))
    ds = Dataset.fetch_rows(s, UnifiedFilter(), SUBSET_6, user=user, today=TODAY)
    generate_json_report(s, UnifiedFilter(), SUBSET_6, tmp_path / "g.json", user=user)
    doc = json.loads((tmp_path / "g.json").read_text(encoding="utf-8"))
    assert doc["totals"]["row_count"] == ds.total == 1
    assert doc["rows"][0]["university"] == "ВУЗ Гамма"


# ------------------------------------------------------- cross-format consistency


def _xlsx_data_rows(path, ncols):
    from openpyxl import load_workbook

    ws = load_workbook(path)["Отчёт"]
    rows = []
    r = HEADER_ROW + 1
    while True:
        values = [ws.cell(row=r, column=c).value for c in range(1, ncols + 1)]
        if all(v is None for v in values):
            break
        rows.append(values)
        r += 1
        if r > HEADER_ROW + 10000:
            break
    return rows


def test_cross_format_same_rows_columns_values(fx):
    s, _, _, tmp_path = fx
    filters = UnifiedFilter()
    ds = Dataset.fetch_rows(s, filters, SUBSET_6, today=TODAY)
    streamed = list(Dataset.iterate_rows(s, filters, SUBSET_6, today=TODAY))
    assert streamed == ds.rows  # fetch (PDF) vs iterate (XLSX/JSON) identical

    xlsx = generate_xlsx_report(s, filters, SUBSET_6, tmp_path / "c.xlsx")
    pdf = generate_pdf_report(s, filters, SUBSET_6, tmp_path / "c.pdf")
    js = generate_json_report(s, filters, SUBSET_6, tmp_path / "c.json")
    assert (xlsx.row_count, pdf.row_count, js.row_count) == (ds.total,) * 3 == (5, 5, 5)
    assert xlsx.columns == pdf.columns == js.columns == SUBSET_6

    ws_rows = _xlsx_data_rows(xlsx.path, len(SUBSET_6))
    assert len(ws_rows) == 5
    doc = json.loads((tmp_path / "c.json").read_text(encoding="utf-8"))
    for idx, ds_row in enumerate(ds.rows):
        # XLSX: same values (empty cells are None; no placeholders).
        for col, key in enumerate(SUBSET_6):
            expected = ds_row[key]
            assert ws_rows[idx][col] == expected, (idx, key)
        # JSON: identical items (SUBSET_6 is str/int/None).
        assert doc["rows"][idx] == ds_row

    pdf_text = _nospace(extract_pdf_text(pdf.path.read_bytes()))
    for probe in ("МГУ им. Ломоносова", "ВУЗ Бета", "ВУЗ Гамма", "ВУЗ Дельта"):
        assert _nospace(probe) in pdf_text
    # Same null behavior: fallback rows render empty (never placeholders).
    assert "None" not in pdf_text and "N/A" not in pdf_text


def test_cross_format_filtered_subset(fx):
    s, _, ids, tmp_path = fx
    # The period is the INTERACTION period (ТЗ), so an interaction must exist
    # inside the range for the university to be selected.
    filters = UnifiedFilter(
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
        university_ids=[ids["mgu"]],
    )
    cols = ["university", "product", "workflow_progress"]
    ds = Dataset.fetch_rows(s, filters, cols, today=TODAY)
    assert ds.total == 2
    xlsx = generate_xlsx_report(s, filters, cols, tmp_path / "f.xlsx")
    pdf = generate_pdf_report(s, filters, cols, tmp_path / "f.pdf")
    generate_json_report(s, filters, cols, tmp_path / "f.json")
    doc = json.loads((tmp_path / "f.json").read_text(encoding="utf-8"))
    assert xlsx.row_count == pdf.row_count == doc["totals"]["row_count"] == 2
    products = sorted(i["product"] for i in doc["rows"])
    assert products == ["ПО Второе", "ПО Защита"]
    # The filter is scoped to МГУ, whose 1-of-2 completed stages give 50%
    # on both of its license rows.
    assert {i["workflow_progress"] for i in doc["rows"]} == {50}


# ------------------------------------------------------- volume probes


def test_json_large_export_bounded(fx):
    s, _, _, tmp_path = fx
    vendor = Vendor(id=uuid4(), name="Массовый Вендор")
    product = ITProduct(id=uuid4(), vendor_id=vendor.id, name="Массовое ПО")
    s.add_all([vendor, product])
    s.flush()
    extra_unis, extra_licenses, extra_meetings = [], [], []
    for i in range(1500):
        uid = uuid4()
        extra_unis.append(
            University(id=uid, name=f"Массовый ВУЗ {i:04d}", created_at=_utc(2026, 6, 1))
        )
        # One interaction inside the filtered period: the ТЗ period is the
        # interaction period, not the university creation date.
        extra_meetings.append(
            Meeting(
                id=uuid4(),
                university_id=uid,
                meeting_type="online",
                subject=f"Встреча {i}",
                participants=[],
                meeting_at=_utc(2026, 6, 1),
                created_by_keycloak_sub="tester",
            )
        )
        extra_licenses.append(
            License(
                id=uuid4(),
                university_id=uid,
                product_id=product.id,
                contract_id=None,
                program_id=None,
                direction_id=None,
                license_number=f"M-{i:04d}",
                signed_at=date(2026, 6, 1),
                expires_at=date(2027, 6, 1),
                transfer_status_raw=None,
                comment=None,
            )
        )
    s.add_all(extra_unis)
    s.flush()
    s.add_all(extra_licenses)
    s.add_all(extra_meetings)
    s.commit()
    filters = UnifiedFilter(date_from=date(2026, 6, 1), date_to=date(2026, 6, 1))
    ds = Dataset.fetch_rows(s, filters, SUBSET_6, today=TODAY)
    assert ds.total == 1500
    result = generate_json_report(s, filters, SUBSET_6, tmp_path / "big.json")
    assert result.row_count == 1500
    doc = json.loads((tmp_path / "big.json").read_text(encoding="utf-8"))
    assert doc["totals"]["row_count"] == 1500 and len(doc["rows"]) == 1500


def test_pdf_multipage_volume(fx):
    s, _, _, tmp_path = fx
    paging = []
    for i in range(200):
        uid = uuid4()
        paging.append(University(id=uid, name=f"Пейджинговый ВУЗ {i:03d}",
                                 created_at=_utc(2026, 6, 2)))
    s.add_all(paging)
    s.flush()
    s.add_all([
        Meeting(
            id=uuid4(),
            university_id=u.id,
            meeting_type="online",
            subject=f"Пейджинговая встреча {i}",
            participants=[],
            meeting_at=_utc(2026, 6, 2),
            created_by_keycloak_sub="tester",
        )
        for i, u in enumerate(paging)
    ])
    s.commit()
    filters = UnifiedFilter(date_from=date(2026, 6, 2), date_to=date(2026, 6, 2))
    result = generate_pdf_report(s, filters, SUBSET_6, tmp_path / "pages.pdf")
    assert result.row_count == 200
    counts = [int(n) for n in re.findall(rb"/Count (\d+)", result.path.read_bytes())]
    assert counts and max(counts) >= 2
