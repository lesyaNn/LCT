"""P4-12-01 golden cross-check: one seed, same numbers everywhere (PG only).

The spec's sample numbers are contradictory (see P4_DEV2_HANDOFF), so this
test freezes a minimal deterministic seed and asserts the core acceptance
invariant: list count == dataset total == overview KPI == xlsx/json/pdf row
counts. Any drift between list/analytics/exports fails loudly here instead
of surprising P3/INT-06.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models.catalog import ITProduct, License, University, Vendor
from app.models.health_score import HealthScoreSnapshot

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")


def _seed(db: Session) -> None:
    vendor = Vendor(id=uuid.uuid4(), name="Вендор Г")
    product = ITProduct(id=uuid.uuid4(), vendor_id=vendor.id, name="ПО Голд")
    alpha = University(id=uuid.uuid4(), name="Альфа-Г")
    beta = University(id=uuid.uuid4(), name="Бета-Г")
    db.add_all([vendor, product, alpha, beta])
    db.flush()
    db.add(
        License(
            id=uuid.uuid4(),
            university_id=alpha.id,
            product_id=product.id,
            contract_id=None,
            program_id=None,
            direction_id=None,
            license_number="GLD-1",
            signed_at=date(2026, 1, 10),
            expires_at=date(2027, 1, 10),
            transfer_status_raw="accepted",
            comment=None,
        )
    )
    db.add(
        HealthScoreSnapshot(
            id=uuid.uuid4(),
            university_id=alpha.id,
            score=80,
            status="yellow",
            breakdown={},
            reasons=[],
            calculated_at=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
            period_day=date(2026, 9, 20),
            trigger_event="daily",
        )
    )
    db.commit()


def test_golden_counts_match_across_list_dataset_overview_exports(tmp_path):
    from tests.db_helpers import require_pg_engine

    eng = require_pg_engine(TEST_URL)
    try:
        from app.modules.analytics.analytics import AnalyticsService
        from app.modules.analytics.dataset import ReportDatasetService
        from app.modules.analytics.filters import UnifiedFilter
        from app.modules.analytics.integration import Selection
        from app.modules.analytics.json_export import generate_json_report
        from app.modules.analytics.repository import load_data
        from app.modules.analytics.service import build_overview
        from app.modules.analytics.xlsx import generate_xlsx_report

        filters = UnifiedFilter()
        with Session(eng) as db:
            _seed(db)
            universities = AnalyticsService.filtered_university_ids(db, filters)
            assert len(universities) == 2

            ds = ReportDatasetService.fetch_rows(db, filters, None)
            # Альфа-Г: 1 license row; Бета-Г: 1 fallback row.
            assert ds.total == 2
            assert ds.university_count == 2

            selection = Selection(university_ids=list(universities), program_ids=[])
            overview = build_overview(
                load_data(db, selection, today=date(2026, 9, 20)),
                today=date(2026, 9, 20),
            )
            assert overview.kpi.universities == 2

            xlsx = generate_xlsx_report(db, filters, None, tmp_path / "g.xlsx")
            assert xlsx.row_count == 2
            js = generate_json_report(db, filters, None, tmp_path / "g.json")
            assert js.row_count == 2
            doc = json.loads((tmp_path / "g.json").read_text(encoding="utf-8"))
            assert doc["totals"]["row_count"] == 2
            assert doc["totals"]["universities"] == 2

            try:
                from app.modules.analytics.pdf import generate_pdf_report

                pdf = generate_pdf_report(db, filters, None, tmp_path / "g.pdf")
                assert pdf.row_count == 2
            except ImportError:
                pass  # reportlab absent in this env; CI image has it
    finally:
        eng.dispose()
