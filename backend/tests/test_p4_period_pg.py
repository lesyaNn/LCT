"""PG integration tests for the ТЗ period semantics (interaction period).

The period filters the selection by **interaction date** (``meetings.meeting_at``
OR ``interaction_notes.created_at``), not by the university creation date and
not by license/contract dates. These tests pin that behaviour, including the
two consequences that are easy to get wrong:

* a university with several interactions in the range is still returned once,
  following the dataset grain ``University x License`` — the period is a
  membership test, not a row multiplier;
* a university with no interactions at all drops out as soon as any bound is
  set, and comes back when the period is cleared.

No database-less test can prove this, so it runs against real PostgreSQL.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models.catalog import ITDirection, ITProduct, ITProgram, License, University, Vendor
from app.models.interactions import InteractionNote, Meeting, UniversityProduct
from app.modules.analytics.dataset import ReportDatasetService as Dataset
from app.modules.analytics.filters import UnifiedFilter
from app.modules.analytics.xlsx import generate_xlsx_report
from tests.db_helpers import require_pg_engine

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")
TODAY = date(2026, 9, 20)
COLS = ["university", "product"]


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def session():
    eng = require_pg_engine(TEST_URL)
    with Session(eng) as s:
        yield s
    eng.dispose()


def _seed(s: Session) -> dict:
    """Two universities with different interaction histories.

    * ``two_meetings`` — two meetings inside September 2026;
    * ``september_note`` — a single interaction note in September 2026;
    * ``august_only`` — interactions only in August 2026;
    * ``never`` — no interactions at all.
    All four are created in June 2026, so a creation-date filter would match
    all of them and cannot be confused with the interaction filter.
    """
    direction = ITDirection(id=uuid4(), code="TZD", name="Направление ТЗ")
    program = ITProgram(id=uuid4(), direction_id=direction.id, name="Программа ТЗ")
    vendor = Vendor(id=uuid4(), name="Вендор ТЗ")
    product = ITProduct(id=uuid4(), vendor_id=vendor.id, name="ПО ТЗ")
    unis = {
        key: University(id=uuid4(), name=name, created_at=_utc(2026, 6, 1))
        for key, name in (
            ("two_meetings", "ВУЗ Две встречи"),
            ("september_note", "ВУЗ Заметка"),
            ("august_only", "ВУЗ Август"),
            ("never", "ВУЗ Без взаимодействий"),
        )
    }
    s.add_all([direction, program, vendor, product, *unis.values()])
    s.flush()
    for university in unis.values():
        s.add(
            License(
                id=uuid4(),
                university_id=university.id,
                product_id=product.id,
                contract_id=None,
                program_id=program.id,
                direction_id=direction.id,
                license_number=f"L-{university.name}",
                signed_at=date(2026, 6, 1),
                expires_at=date(2027, 6, 1),
                transfer_status_raw="transferred",
                comment=None,
            )
        )
        s.add(UniversityProduct(university_id=university.id, product_id=product.id))
    s.add_all([
        Meeting(id=uuid4(), university_id=unis["two_meetings"].id,
                meeting_type="online", subject="Первая", participants=[],
                meeting_at=_utc(2026, 9, 10), created_by_keycloak_sub="t"),
        Meeting(id=uuid4(), university_id=unis["two_meetings"].id,
                meeting_type="online", subject="Вторая", participants=[],
                meeting_at=_utc(2026, 9, 20), created_by_keycloak_sub="t"),
        Meeting(id=uuid4(), university_id=unis["august_only"].id,
                meeting_type="online", subject="Августовская", participants=[],
                meeting_at=_utc(2026, 8, 15), created_by_keycloak_sub="t"),
    ])
    # ``created_at`` is set explicitly: the model would otherwise stamp "now",
    # which silently moves the interaction into whatever period is under test.
    s.add_all([
        InteractionNote(
            id=uuid4(),
            university_id=unis["september_note"].id,
            author_keycloak_sub="t",
            content="Сентябрьская заметка",
            is_internal=True,
            created_at=_utc(2026, 9, 12),
        ),
    ])
    s.commit()
    return unis


def _selected(session: Session, filters: UnifiedFilter) -> set[str]:
    ds = Dataset.fetch_rows(session, filters, COLS, today=TODAY)
    return {row["university"] for row in ds.rows}


def test_period_selects_universities_with_interactions_inside_the_range(session):
    unis = _seed(session)
    found = _selected(
        session, UnifiedFilter(date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))
    )
    assert found == {unis["two_meetings"].name, unis["september_note"].name}
    # Interactions outside the range do not qualify, and neither does the
    # absence of any interaction.
    assert unis["august_only"].name not in found
    assert unis["never"].name not in found


def test_several_interactions_do_not_duplicate_rows(session):
    """The period is a membership test, not a row multiplier.

    ``two_meetings`` has two meetings in the range and still yields exactly
    its own dataset grain (University x License = 1 row here), not two rows.
    """
    _seed(session)
    filters = UnifiedFilter(date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))
    ds = Dataset.fetch_rows(session, filters, COLS, today=TODAY)
    per_university: dict[str, int] = {}
    for row in ds.rows:
        per_university[row["university"]] = per_university.get(row["university"], 0) + 1
    assert per_university["ВУЗ Две встречи"] == 1
    assert sum(per_university.values()) == ds.total == 2


def test_creation_date_is_not_used_by_the_period(session):
    """All four universities were created in June 2026, so a June filter must
    return nothing — proving the period does not read ``universities.created_at``."""
    _seed(session)
    found = _selected(
        session, UnifiedFilter(date_from=date(2026, 6, 1), date_to=date(2026, 6, 30))
    )
    assert found == set()


def test_no_period_keeps_universities_without_interactions(session):
    _seed(session)
    found = _selected(session, UnifiedFilter())
    assert "ВУЗ Без взаимодействий" in found
    assert len(found) == 4


def test_open_ended_bounds(session):
    _seed(session)
    from_september = _selected(session, UnifiedFilter(date_from=date(2026, 9, 1)))
    assert from_september == {"ВУЗ Две встречи", "ВУЗ Заметка"}
    until_september = _selected(session, UnifiedFilter(date_to=date(2026, 9, 30)))
    assert "ВУЗ Август" in until_september
    assert "ВУЗ Без взаимодействий" not in until_september


def test_bounds_are_inclusive_on_both_ends(session):
    """A single-day range must match an interaction on exactly that day."""
    _seed(session)
    only_10th = _selected(
        session, UnifiedFilter(date_from=date(2026, 9, 10), date_to=date(2026, 9, 10))
    )
    assert only_10th == {"ВУЗ Две встречи"}


def test_period_combines_with_other_dimensions_with_and(session):
    """AND between dimensions: period narrows, university_ids narrows further."""
    unis = _seed(session)
    filters = UnifiedFilter(
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
        university_ids=[unis["september_note"].id],
    )
    assert _selected(session, filters) == {unis["september_note"].name}
    # Contradictory combination -> empty, never an error.
    contradictory = UnifiedFilter(
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
        university_ids=[unis["never"].id],
    )
    assert _selected(session, contradictory) == set()


def test_export_respects_the_same_period_as_the_dataset(session, tmp_path):
    """The export path applies the same period, not a second interpretation."""
    _seed(session)
    filters = UnifiedFilter(date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))
    ds = Dataset.fetch_rows(session, filters, COLS, today=TODAY)
    report = generate_xlsx_report(session, filters, COLS, tmp_path / "period.xlsx")
    assert report.row_count == ds.total == 2
