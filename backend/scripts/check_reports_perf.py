"""Measure the report path at production-ish scale and prove the indexes.

Answers two ТЗ questions with numbers instead of guesses:

1. how long a filter change takes (preview), and
2. which of the report queries need an index.

Run after ``scripts/migrate.py up`` + ``python -m app.db.seed`` +
``python scripts/seed_performance.py``::

    DATABASE_URL=... python scripts/check_reports_perf.py
    DATABASE_URL=... python scripts/check_reports_perf.py --scale 3

``--scale N`` multiplies the interaction volume before measuring, which is how
the index decision was made: the report SQL is measured at 1x and at Nx so a
regression shows up as a slope rather than as one lucky number.
"""

from __future__ import annotations

import argparse
import datetime
import os
import random
import sys
import time
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import event, select, text  # noqa: E402

from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.catalog import University  # noqa: E402
from app.models.interactions import InteractionNote, Meeting  # noqa: E402
from app.modules.analytics.dataset import ReportDatasetService  # noqa: E402
from app.modules.analytics.filters import UnifiedFilter  # noqa: E402
from app.modules.analytics.stats import ReportStatsService  # noqa: E402

TZ_COLUMNS = ["university", "direction", "product", "workflow_status", "responsible"]
FULL_COLUMNS = [*TZ_COLUMNS, "program", "vendor", "contract_number", "city",
                "last_interaction", "workflow_progress", "overdue_tasks"]


def _utc(days_back: int) -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_back)


def volume() -> dict[str, int]:
    with engine.connect() as conn:
        return {
            table: conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
            for table in ("universities", "licenses", "meetings", "interaction_notes")
        }


def scale_interactions(factor: int) -> None:
    """Multiply meetings/notes by copying recent rows with a fresh marker."""
    if factor <= 1:
        return
    rng = random.Random(42)
    with SessionLocal() as session, session.begin():
        unis = session.execute(select(University.id)).scalars().all()
        for copy in range(1, factor + 1):
            session.add_all([
                Meeting(
                    id=uuid4(),
                    university_id=unis[i % len(unis)],
                    meeting_type="online",
                    subject=f"perf scale {copy}-{i}",
                    participants=[],
                    meeting_at=_utc(rng.randint(0, 700)),
                    created_by_keycloak_sub="perf-scale",
                )
                for i in range(len(unis))
            ])
            session.add_all([
                InteractionNote(
                    id=uuid4(),
                    university_id=unis[i % len(unis)],
                    author_keycloak_sub="perf-scale",
                    content=f"perf scale {copy}-{i}",
                    is_internal=True,
                    created_at=_utc(rng.randint(0, 700)),
                )
                for i in range(len(unis))
            ])


def _timed(fn, repeats: int = 5) -> tuple[float, object]:
    """Median-ish: best of N, which is the least noisy signal for a latency SLO."""
    best = float("inf")
    result = None
    for _ in range(repeats):
        start = time.perf_counter()
        result = fn()
        best = min(best, time.perf_counter() - start)
    return best, result


def measure(label: str) -> None:
    today = datetime.date.today()
    period = UnifiedFilter(
        date_from=today - datetime.timedelta(days=365), date_to=today
    )
    counters = {"select": 0, "statements": []}

    def watch(conn, cursor, statement, parameters, context, executemany):
        counters["select"] += 1
        if counters["select"] <= 40:
            counters["statements"].append(" ".join(statement.split())[:120])

    event.listen(engine, "before_cursor_execute", watch)
    try:
        with SessionLocal() as session:
            preview_s, preview = _timed(
                lambda: ReportDatasetService.fetch_preview(
                    session, period, TZ_COLUMNS, limit=50
                )
            )
            print(f"\n--- {label}: volume {volume()}")
            print(f"  preview (LIMIT 50)      {preview_s * 1000:7.1f} ms  "
                  f"total={preview.total} universities={preview.university_count}")

            dataset_s, dataset = _timed(
                lambda: ReportDatasetService.fetch_rows(
                    session, period, FULL_COLUMNS
                )
            )
            print(f"  full dataset (FULL cols){dataset_s * 1000:7.1f} ms  rows={dataset.total}")

            stats_s, stats = _timed(
                lambda: ReportStatsService.build(session, period, today=today)
            )
            print(f"  statistics (SQL GROUP BY){stats_s * 1000:6.1f} ms  "
                  f"universities={stats.university_count} rows={stats.row_count}")
            for sl in stats.slices:
                print(f"      {sl.dimension:20} buckets={len(sl.buckets):2} total={sl.total}")

            print(f"  statements for the three calls: {counters['select']}")
            for statement in counters["statements"][:12]:
                print(f"      {statement}")
    finally:
        event.remove(engine, "before_cursor_execute", watch)


def explain(label: str, which: str) -> None:
    today = datetime.date.today()
    period = UnifiedFilter(
        date_from=today - datetime.timedelta(days=365), date_to=today
    )
    with SessionLocal() as session:
        if which == "dataset":
            stmt = ReportDatasetService.build_query(period, TZ_COLUMNS, today=today)
        else:
            stmt = ReportStatsService._filtered_rows(period, user=None, today=today).stmt
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        print(f"\n===== EXPLAIN {label} / {which} =====")
        for (line,) in session.execute(
            text("EXPLAIN (ANALYZE, BUFFERS) " + sql)
        ).all():
            print("  ", line[:165])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report path performance probe")
    parser.add_argument("--scale", type=int, default=1, help="multiply interactions before measuring")
    parser.add_argument("--explain", choices=["dataset", "stats"], help="also print a plan")
    args = parser.parse_args(argv)

    scale_interactions(args.scale)
    measure(f"scale x{args.scale}")
    if args.explain:
        explain(f"scale x{args.scale}", args.explain)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
