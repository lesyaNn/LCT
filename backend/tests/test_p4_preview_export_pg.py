"""Preview is bounded; the export is not (ТЗ §4 steps 8–11, §10).

The two paths must be distinguished deliberately: the preview exists so the
UI can react to a filter change fast, so it is capped. An export must never
inherit that cap, otherwise the user would download a silently truncated file
while the UI showed a larger row count.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
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
from app.modules.analytics.xlsx import DATA_START_ROW, HEADER_ROW, generate_xlsx_report
from tests.db_helpers import require_pg_engine

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")
TODAY = date(2026, 9, 20)
PREVIEW_LIMIT = 50
#: Comfortably above PREVIEW_LIMIT, so a leaked cap is visible.
UNIVERSITY_COUNT = 120


def _client(user: CurrentUser, session: Session) -> TestClient:
    """Minimal app with just the reports router; auth + DB overridden.

    The router resolves its session through ``get_audit_db`` (which wraps
    ``get_db``), so both the user and the session are injected — otherwise the
    handler would query the default ``DATABASE_URL`` instead of the test schema.
    """
    from fastapi import FastAPI

    from app.core.errors import register_error_handlers
    from app.core.security import get_current_user
    from app.modules.analytics.reports_router import router as reports_router
    from app.modules.audit.service import get_audit_db

    api = FastAPI()
    register_error_handlers(api)
    api.include_router(reports_router)
    api.dependency_overrides[get_current_user] = lambda: user
    api.dependency_overrides[get_audit_db] = lambda: session
    return TestClient(api, raise_server_exceptions=False)


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def session():
    eng = require_pg_engine(TEST_URL)
    with Session(eng) as s:
        yield s
    eng.dispose()


@pytest.fixture()
def many_universities(session):
    """UNIVERSITY_COUNT universities, each with 2 licenses and a meeting."""
    direction = ITDirection(id=uuid4(), code="PV", name="Направление Превью")
    program = ITProgram(id=uuid4(), direction_id=direction.id, name="Программа Превью")
    vendor = Vendor(id=uuid4(), name="Вендор Превью")
    product = ITProduct(id=uuid4(), vendor_id=vendor.id, name="ПО Превью")
    responsible = Responsible(id=uuid4(), full_name="Ответственный Превью", email="pv@x.local")
    unis = [
        University(id=uuid4(), name=f"ВУЗ {i:03d}", created_at=_utc(2026, 6, 1))
        for i in range(UNIVERSITY_COUNT)
    ]
    session.add_all([direction, program, vendor, product, responsible, *unis])
    session.flush()
    session.add_all([
        Meeting(
            id=uuid4(),
            university_id=u.id,
            meeting_type="online",
            subject=f"Встреча {i}",
            participants=[],
            meeting_at=_utc(2026, 9, 5),
            created_by_keycloak_sub="t",
        )
        for i, u in enumerate(unis)
    ])
    for u in unis:
        session.add_all([
            UniversityProduct(university_id=u.id, product_id=product.id),
            UniversityResponsible(university_id=u.id, responsible_id=responsible.id),
        ])
        for n in (1, 2):
            session.add(License(
                id=uuid4(),
                university_id=u.id,
                product_id=product.id,
                contract_id=None,
                program_id=program.id,
                direction_id=direction.id,
                license_number=f"L-{u.name}-{n}",
                signed_at=date(2026, 6, 1),
                expires_at=date(2027, 6, 1),
                transfer_status_raw="transferred",
                comment=None,
            ))
    session.commit()
    return unis


def test_preview_is_capped_but_total_reports_the_full_selection(session, many_universities):
    filters = UnifiedFilter(date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))
    preview = ReportDatasetService.fetch_preview(
        session, filters, ["university", "product"], limit=PREVIEW_LIMIT
    )
    assert len(preview.rows) == PREVIEW_LIMIT
    # The cap must NOT be reflected in `total`: that is the export size the UI
    # shows, so a user can tell the report is bigger than the preview.
    assert preview.total == UNIVERSITY_COUNT * 2
    assert preview.total > len(preview.rows)


def test_export_contains_every_row_not_just_the_preview_page(
    session, many_universities, tmp_path
):
    filters = UnifiedFilter(date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))
    cols = ["university", "product"]
    report = generate_xlsx_report(session, filters, cols, tmp_path / "full.xlsx")
    expected = UNIVERSITY_COUNT * 2
    assert report.row_count == expected
    assert report.row_count > PREVIEW_LIMIT

    sheet = load_workbook(report.path)["Отчёт"]
    written = [
        sheet.cell(row=r, column=1).value
        for r in range(DATA_START_ROW, DATA_START_ROW + expected)
    ]
    assert len(written) == expected
    assert all(name for name in written), "no empty trailing rows"
    # Every university in the export, not just the first 25 preview ones.
    assert len(set(written)) == UNIVERSITY_COUNT
    assert sheet.cell(HEADER_ROW, 1).value == "Наименование ВУЗа"


def test_preview_and_export_agree_on_the_first_page(session, many_universities):
    """The same filters must give the same rows, in the same order."""
    filters = UnifiedFilter(date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))
    cols = ["university", "product"]
    preview = ReportDatasetService.fetch_preview(
        session, filters, cols, limit=PREVIEW_LIMIT
    )
    full = ReportDatasetService.fetch_rows(session, filters, cols, today=TODAY)
    assert preview.rows == full.rows[:PREVIEW_LIMIT]
    assert preview.total == full.total


def test_preview_limit_must_be_positive(session, many_universities):
    with pytest.raises(ValueError, match="limit"):
        ReportDatasetService.fetch_preview(
            session, UnifiedFilter(), ["university"], limit=0
        )


def test_preview_respects_the_security_scope(session, many_universities):
    """A scoped user must not see other universities through the preview.

    ``product`` is a license-grain column, so the selection is 2 rows for the
    scoped university and 0 for the other 119.
    """
    scoped_id = str(many_universities[0].id)
    user = CurrentUser(id="scoped", roles={"manager"}, university_ids=(scoped_id,))
    filters = UnifiedFilter(date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))
    preview = ReportDatasetService.fetch_preview(
        session, filters, ["university", "product"], limit=PREVIEW_LIMIT, user=user
    )
    assert preview.total == 2
    assert {row["university"] for row in preview.rows} == {many_universities[0].name}
    # The scope is conjunctive: it can only narrow, never widen.
    assert preview.total < ReportDatasetService.fetch_rows(
        session, filters, ["university", "product"], today=TODAY
    ).total


def test_university_only_selection_is_one_row_per_university(session, many_universities):
    """Row grain follows the selected columns (pre-existing dataset rule).

    With only ``university`` selected the dataset needs no license join, so the
    selection is one row per university. This is asserted so the preview tests
    below do not read as a regression when they expect 2 rows for 2 licenses.
    """
    university_only = ReportDatasetService.fetch_preview(
        session,
        UnifiedFilter(date_from=date(2026, 9, 1), date_to=date(2026, 9, 30)),
        ["university"],
        limit=PREVIEW_LIMIT,
    )
    assert university_only.total == UNIVERSITY_COUNT


def test_preview_endpoint_returns_a_bounded_page(session, many_universities):
    """HTTP contract: rows are capped, ``total`` is not, no private keys leak."""
    user = CurrentUser(id="admin-preview", roles={"admin", "*"}, university_ids=None)
    client = _client(user, session)
    body = {
        "format": "xlsx",
        "filters": {"date_from": "2026-09-01", "date_to": "2026-09-30"},
        "columns": ["university", "product"],
    }
    response = client.post("/reports/preview", json=body)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["rows"]) <= payload["preview_limit"]
    assert payload["total"] == UNIVERSITY_COUNT * 2
    assert payload["columns"] == ["university", "product"]
    assert all(not key.startswith("_") for row in payload["rows"] for key in row)


def test_preview_endpoint_rejects_an_unknown_column(session, many_universities):
    user = CurrentUser(id="admin-preview", roles={"admin", "*"}, university_ids=None)
    client = _client(user, session)
    response = client.post(
        "/reports/preview", json={"format": "xlsx", "columns": ["university", "nope"]}
    )
    assert response.status_code == 422, response.text
