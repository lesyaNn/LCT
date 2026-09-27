"""10 parallel reports of varying complexity (ТЗ §2 performance).

Runs the real export path — filter application, dataset query, statistics and
file generation — for ten concurrent jobs, each with a different filter and a
different column set, and asserts that:

* all ten succeed;
* every generated file is a valid, non-empty artifact of its format;
* the selection of each report matches what the same filter produces on its
  own (concurrency must not let one report read another's data);
* the wall clock stays inside a sane bound, reported alongside the numbers
  rather than asserted on a machine-specific threshold.

Everything runs against real PostgreSQL, because the point of the exercise is
the DB behaviour under concurrency, not the Python.
"""

from __future__ import annotations

import datetime
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.security import CurrentUser
from sqlalchemy.orm import sessionmaker
from app.modules.analytics.filters import UnifiedFilter
from app.modules.analytics.report_request import ReportRequest
from app.modules.analytics.report_service import generate_report_file
from app.modules.analytics.stats import ReportStatsService
from tests.db_helpers import require_pg_engine

TEST_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")
TODAY = datetime.date.today()
PARALLEL_REPORTS = 10

USER = CurrentUser(id="perf-parallel", roles={"admin", "*"}, university_ids=None)

#: Ten genuinely different selections: different periods, different column
#: sets (ТЗ default vs FULL), different formats. Identical jobs would let one
#: cached result mask a concurrency bug.
JOBS = [
    {"format": "xls", "columns": None, "days": 365, "university": 0},
    {"format": "xlsx", "columns": ["university", "direction", "product"], "days": 180, "university": 0},
    {"format": "pdf", "columns": None, "days": 90, "university": 0},
    {"format": "xls", "columns": ["university", "responsible", "workflow_status"], "days": 730, "university": 0},
    {"format": "json", "columns": None, "days": 30, "university": 0},
    {"format": "xlsx", "columns": None, "days": 365, "university": 1},
    {"format": "pdf", "columns": ["university", "product", "workflow_progress", "overdue_tasks"], "days": 200, "university": 1},
    {"format": "xls", "columns": None, "days": 45, "university": 1},
    {"format": "xlsx", "columns": ["university", "city", "last_interaction"], "days": 400, "university": 1},
    {"format": "pdf", "columns": None, "days": 120, "university": 1},
]

MAGIC = {
    "xls": b"\xd0\xcf\x11\xe0",   # OLE2 compound file (BIFF8)
    "xlsx": b"PK\x03\x04",       # ZIP (OOXML)
    "pdf": b"%PDF",
    "json": b"{",
}


def _run_one(spec: dict, uni_ids: list, out_dir: Path, factory) -> dict:
    """One report, in its own session, exactly like the worker would do it.

    ``factory`` is bound to the TEST engine, so the threads really do hit
    PostgreSQL concurrently rather than the app's default database.
    """
    filters = UnifiedFilter(
        date_from=TODAY - datetime.timedelta(days=spec["days"]),
        date_to=TODAY,
        university_ids=[uni_ids[spec["university"]]] if spec["university"] else [],
    )
    request = ReportRequest(
        format=spec["format"], filters=filters, columns=spec["columns"]
    )
    started = time.perf_counter()
    with factory() as session:
        stats = ReportStatsService.build(session, filters, user=USER, today=TODAY)
        result = generate_report_file(
            session, request, out_dir / f"parallel_{spec['format']}_{spec['days']}.out",
            user=USER,
        )
    return {
        "format": spec["format"],
        "rows": result.row_count,
        "columns": result.columns,
        "size": result.size_bytes,
        "stats_rows": stats.row_count,
        "stats_universities": stats.university_count,
        "elapsed": time.perf_counter() - started,
    }


def _seed_workload(session: Session, universities: int = 24) -> list:
    """A workload big enough to be worth parallelising.

    Every university gets meetings and notes spread over the last two years
    (so the period filter has something to match), several licenses (so the
    row grain is University x License) and two responsibles.
    """
    import random

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
    from app.models.interactions import InteractionNote, Meeting, UniversityProduct

    rng = random.Random(7)
    direction = ITDirection(id=uuid4(), code="PP", name="Направление Параллели")
    program = ITProgram(id=uuid4(), direction_id=direction.id, name="Программа Параллели")
    vendor = Vendor(id=uuid4(), name="Вендор Параллели")
    products = [
        ITProduct(id=uuid4(), vendor_id=vendor.id, name=f"ПО Параллели {i}")
        for i in range(4)
    ]
    responsibles = [
        Responsible(id=uuid4(), full_name=f"Ответственный {i}", email=f"par{i}@x.local")
        for i in range(4)
    ]
    unis = [
        University(
            id=uuid4(),
            name=f"ВУЗ Параллели {i:02d}",
            created_at=datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(days=800),
        )
        for i in range(universities)
    ]
    session.add_all([direction, program, vendor, *products, *responsibles, *unis])
    session.flush()

    meetings, notes, licenses = [], [], []
    for index, uni in enumerate(unis):
        for offset in range(6):
            meetings.append(Meeting(
                id=uuid4(), university_id=uni.id, meeting_type="online",
                subject=f"Встреча {offset}", participants=[],
                meeting_at=datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(days=rng.randint(0, 700)),
                created_by_keycloak_sub="parallel",
            ))
        for offset in range(8):
            notes.append(InteractionNote(
                id=uuid4(), university_id=uni.id,
                author_keycloak_sub="parallel",
                content=f"Заметка {offset}", is_internal=True,
                created_at=datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(days=rng.randint(0, 700)),
            ))
        for offset, product in enumerate(products):
            if rng.random() < 0.75:
                contract = Contract(
                    id=uuid4(), university_id=uni.id, product_id=product.id,
                    contract_number=f"PAR-{index}-{offset}",
                    signed_at=TODAY - datetime.timedelta(days=400),
                    expires_at=TODAY + datetime.timedelta(days=200),
                    transfer_status_raw="transferred", comment=None,
                )
                session.add(contract)
                licenses.append(License(
                    id=uuid4(), university_id=uni.id, product_id=product.id,
                    contract_id=contract.id, program_id=program.id,
                    direction_id=direction.id, license_number=f"LP-{index}-{offset}",
                    signed_at=TODAY - datetime.timedelta(days=400),
                    expires_at=TODAY + datetime.timedelta(days=200),
                    transfer_status_raw="transferred", comment=None,
                ))
            session.add(UniversityProduct(university_id=uni.id, product_id=product.id))
        session.add_all([
            UniversityResponsible(
                university_id=uni.id, responsible_id=responsibles[index % len(responsibles)].id
            ),
            UniversityResponsible(
                university_id=uni.id, responsible_id=responsibles[(index + 1) % len(responsibles)].id
            ),
        ])
    session.add_all(meetings + notes + licenses)
    session.commit()
    return [uni.id for uni in unis]


@pytest.fixture()
def workload():
    """Seeded workload plus a session factory bound to the TEST engine."""
    eng = require_pg_engine(TEST_URL)
    with Session(eng) as session:
        ids = _seed_workload(session)
    yield ids, sessionmaker(bind=eng, expire_on_commit=False)
    eng.dispose()


def test_ten_parallel_reports_all_succeed(workload, tmp_path):
    uni_ids, factory = workload

    out_dir = tmp_path / "parallel"
    out_dir.mkdir()
    assert len(JOBS) == PARALLEL_REPORTS
    errors: list[BaseException] = []
    results: list[dict] = []
    lock = threading.Lock()

    def worker(spec: dict) -> None:
        try:
            outcome = _run_one(spec, uni_ids, out_dir, factory)
        except BaseException as exc:  # noqa: BLE001 - reported below
            with lock:
                errors.append(exc)
            return
        with lock:
            results.append(outcome)

    wall_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=PARALLEL_REPORTS) as pool:
        list(pool.map(worker, JOBS))
    wall = time.perf_counter() - wall_start

    assert not errors, f"{len(errors)} of {PARALLEL_REPORTS} reports failed: {errors[:3]}"
    assert len(results) == PARALLEL_REPORTS

    for outcome in results:
        assert outcome["size"] > 0, outcome
        assert outcome["columns"], outcome
    print(
        f"\n{PARALLEL_REPORTS} parallel reports in {wall * 1000:.0f} ms "
        f"(slowest single: {max(r['elapsed'] for r in results) * 1000:.0f} ms)"
    )


def test_parallel_reports_preserve_their_own_selection(workload, tmp_path):
    """Concurrency must not let one report read another's rows."""
    uni_ids, factory = workload
    out_dir = tmp_path / "parallel-selection"
    out_dir.mkdir()

    narrow = {"format": "xls", "columns": None, "days": 365, "university": 0}
    wide = {"format": "xls", "columns": None, "days": 365, "university": 1}
    specs = [dict(narrow, format="xls"), dict(wide, format="xls")]

    with ThreadPoolExecutor(max_workers=2) as pool:
        parallel = list(pool.map(lambda spec: _run_one(spec, uni_ids, out_dir, factory), specs))

    for spec, outcome in zip(specs, parallel, strict=True):
        serial = _run_one(spec, uni_ids, out_dir, factory)
        assert outcome["rows"] == serial["rows"], spec
        assert outcome["stats_rows"] == serial["stats_rows"], spec
        assert outcome["stats_universities"] == serial["stats_universities"], spec

    # The two selections differ, so a shared "last writer wins" bug would show
    # up as identical row counts.
    if uni_ids[0] != uni_ids[1]:
        assert parallel[0]["stats_universities"] != parallel[1]["stats_universities"] or (
            parallel[0]["rows"] != parallel[1]["rows"]
        )


def test_generated_files_have_the_magic_bytes_of_their_format(workload, tmp_path):
    uni_ids, factory = workload
    out_dir = tmp_path / "magic"
    out_dir.mkdir()

    for spec in JOBS:
        filters = UnifiedFilter(
            date_from=TODAY - datetime.timedelta(days=spec["days"]), date_to=TODAY
        )
        request = ReportRequest(
            format=spec["format"], filters=filters, columns=spec["columns"]
        )
        target = out_dir / f"magic_{spec['format']}.bin"
        with factory() as session:
            result = generate_report_file(session, request, target, user=USER)
        head = result.path.read_bytes()[:4]
        assert head.startswith(MAGIC[spec["format"]]), (spec["format"], head)


def test_no_partial_files_are_left_behind(workload, tmp_path, monkeypatch):
    """A generation that fails must not leave a ``.part`` artifact behind.

    The failure is injected deterministically in the row iterator rather than
    by hoping for a real error, so the atomic-write contract is exercised on
    every run instead of only when the database happens to misbehave.
    """
    from app.modules.analytics.xlsx import generate_xlsx_report

    uni_ids, factory = workload
    out_dir = tmp_path / "atomic"
    out_dir.mkdir()
    target = out_dir / "boom.xlsx"

    def _explode(*args, **kwargs):
        raise RuntimeError("database went away mid-export")

    monkeypatch.setattr(
        "app.modules.analytics.xlsx.ReportDatasetService.iterate_rows", _explode
    )
    with factory() as session:
        with pytest.raises(RuntimeError, match="database went away"):
            generate_xlsx_report(
                session, UnifiedFilter(), None, target, user=USER
            )

    assert not target.exists(), "no final file may appear after a failure"
    assert not (out_dir / "boom.xlsx.part").exists(), "the temp file must be removed"
