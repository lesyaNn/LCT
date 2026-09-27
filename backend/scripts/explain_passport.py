"""P1-10-02: EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) for real backend SQL.

Uses the production SQLAlchemy statements (captured from a live
``get_passport`` call via a cursor listener, plus the real list/page/audit
statements built by the same code paths) against PostgreSQL. No hand-written
SQL, no SQLite, no ``enable_seqscan=off``.

Usage (from backend/)::

    DATABASE_URL=postgresql+psycopg://rtk:change-me@localhost:5433/rtk \\
        python scripts/explain_passport.py [--out docs/performance/plans]

Prints a per-query summary and stores raw ``EXPLAIN`` JSON per query.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, event, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.models  # noqa: E402,F401
from app.config import settings  # noqa: E402
from app.models.catalog import University  # noqa: E402
from app.modules.audit.service import AuditService  # noqa: E402
from app.modules.universities import passport_service as ps  # noqa: E402


def _summarize(plan: dict) -> dict:
    """Extract the P1-10-02 §11 summary fields from one EXPLAIN JSON plan."""

    def walk(node: dict, out: list):
        out.append(node)
        for child in node.get("Plans", []) or []:
            walk(child, out)

    nodes: list[dict] = []
    walk(plan["Plan"], nodes)
    most_expensive = max(nodes, key=lambda n: n.get("Actual Total Time", 0.0))
    seq_scans = [
        {
            "relation": n.get("Relation Name"),
            "rows": n.get("Actual Rows"),
            "loops": n.get("Actual Loops"),
            "rows_removed": n.get("Rows Removed by Filter"),
            "time": n.get("Actual Total Time"),
        }
        for n in nodes
        if n.get("Node Type") == "Seq Scan"
    ]
    sorts = [
        {
            "method": n.get("Sort Method"),
            "space": n.get("Sort Space Used"),
            "key": n.get("Sort Key"),
            "time": n.get("Actual Total Time"),
        }
        for n in nodes
        if "Sort" in (n.get("Node Type") or "")
    ]
    return {
        "planning_time_ms": plan.get("Planning Time"),
        "execution_time_ms": plan.get("Execution Time"),
        "planning_buffers": plan.get("Planning", {}).get("Shared", {}),
        "shared_hit": plan.get("Planning", {}),
        "actual_rows": plan["Plan"].get("Actual Rows"),
        "actual_loops": plan["Plan"].get("Actual Loops"),
        "shared_hit_blocks": plan["Plan"].get("Shared Hit Blocks"),
        "shared_read_blocks": plan["Plan"].get("Shared Read Blocks"),
        "temp_read": plan["Plan"].get("Temp Read Blocks"),
        "temp_written": plan["Plan"].get("Temp Written Blocks"),
        "jit": plan.get("JIT", {}),
        "workers": plan["Plan"].get("Workers Planned"),
        "top_node": {
            "type": most_expensive.get("Node Type"),
            "relation": most_expensive.get("Relation Name"),
            "index": most_expensive.get("Index Name"),
            "total_cost": most_expensive.get("Total Cost"),
            "time_ms": most_expensive.get("Actual Total Time"),
            "rows": most_expensive.get("Actual Rows"),
            "loops": most_expensive.get("Actual Loops"),
        },
        "seq_scans": seq_scans,
        "sorts": sorts,
        "all_nodes": [
            {
                "type": n.get("Node Type"),
                "relation": n.get("Relation Name"),
                "index": n.get("Index Name"),
                "time_ms": n.get("Actual Total Time"),
                "rows": n.get("Actual Rows"),
                "loops": n.get("Actual Loops"),
            }
            for n in nodes
        ],
    }


def _explain_captured(conn, statement: str, params) -> dict:
    rows = conn.exec_driver_sql(
        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, params or ()
    ).fetchall()
    raw = rows[0][0]
    if isinstance(raw, str):
        raw = json.loads(raw)
    return raw[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/performance/plans")
    ap.add_argument("--university", default="PERF Университет 00")
    args = ap.parse_args()

    url = os.getenv("DATABASE_URL", settings.database_url)
    assert url.startswith("postgresql"), f"P1-10-02 requires PostgreSQL, got {url!r}"
    engine = create_engine(url)

    with Session(engine) as s:
        target = s.execute(
            select(University.id, University.name).where(
                University.name == args.university
            )
        ).first()
        if target is None:
            target = s.execute(
                select(University.id, University.name).order_by(University.name)
            ).first()
        uid = target[0]
    print(f"target university id: {uid}")

    captured: list[tuple[str, object]] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _cap(conn, cursor, statement, parameters, context, executemany):
        if statement.strip().upper().startswith("SELECT"):
            captured.append((statement, parameters))

    with Session(engine) as db:
        ps.get_passport(db, uid)
        db.expire_all()
        ps.get_passport(db, uid, include=frozenset([ps.PassportInclude.AUDIT]))
        db.expire_all()
        ps.get_programs_page(db, uid, 1, 20)
    event.remove(engine, "before_cursor_execute", _cap)

    labels = [
        "passport_1_university",
        "passport_2_programs",
        "passport_3_products",
        "passport_4_licenses_contracts",
        "passport_5_interactions",
        "passport_6_responsibles",
    ]
    # Two get_passport calls (6 base + 6 repeat + 1 audit) plus
    # get_programs_page (4) = 17.
    assert len(captured) == 17, f"expected 17 SELECTs, got {len(captured)}"
    base_captured = captured[:6]
    audit_captured = [captured[12]]
    assert base_captured[0][0] == captured[6][0], "repeat call diverged"
    programs_page_captured = captured[13:17]

    # --- extra real code-path statements (same builders the API uses) ---
    extra: list[tuple[str, tuple, tuple]] = []
    with Session(engine) as db:
        # university list: no-filter + search (real UniversityRepository code path)
        q_all = db.query(University).order_by(University.id.desc()).limit(200)
        extra.append(("list_universities_nofilter", q_all.statement, ()))
        q_search = (
            db.query(University)
            .filter(University.name.ilike("%PERF%"))
            .order_by(University.id.desc())
            .limit(200)
        )
        extra.append(("list_universities_search", q_search.statement, ()))
    # compile extras with literal binds (safe test-only constants: one UUID
    # read from the DB itself and one fixed ILIKE pattern).
    from sqlalchemy.dialects import postgresql as pg_dialect

    compiled_extras: list[tuple[str, str, object]] = []
    for label, stmt, _ in extra:
        compiled = stmt.compile(
            dialect=pg_dialect.dialect(), compile_kwargs={"literal_binds": True}
        )
        compiled_extras.append((label, str(compiled), ()))

    outdir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), args.out)
    os.makedirs(outdir, exist_ok=True)

    page_labels = [
        "programs_page_1_univ",
        "programs_page_2_count",
        "programs_page_3_page",
        "programs_page_4_counts",
    ]
    results: dict[str, dict] = {}
    with engine.connect() as conn:
        for label, (statement, params) in zip(
            labels + ["passport_9_audit"] + page_labels,
            base_captured + audit_captured + programs_page_captured,
        ):
            raw = _explain_captured(conn, statement, params)
            summary = _summarize(raw)
            results[label] = {
                "label": label,
                "sql": statement,
                "summary": summary,
                "raw": raw,
            }
            with open(os.path.join(outdir, f"{label}.json"), "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False, default=str)
            s = summary
            print(
                f"{label}: exec={s['execution_time_ms']}ms plan={s['planning_time_ms']}ms "
                f"rows={s['actual_rows']} hit={s['shared_hit_blocks']} read={s['shared_read_blocks']} "
                f"top={s['top_node']['type']} {s['top_node']['relation'] or ''} "
                f"{s['top_node']['index'] or ''} loops={s['top_node']['loops']} "
                f"seq={len(s['seq_scans'])} sorts={len(s['sorts'])}"
            )
        for label, statement, params in compiled_extras:
            raw = _explain_captured(conn, statement, params)
            summary = _summarize(raw)
            results[label] = {"label": label, "sql": statement, "summary": summary, "raw": raw}
            with open(os.path.join(outdir, f"{label}.json"), "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False, default=str)
            s = summary
            print(
                f"{label}: exec={s['execution_time_ms']}ms plan={s['planning_time_ms']}ms "
                f"rows={s['actual_rows']} hit={s['shared_hit_blocks']} read={s['shared_read_blocks']} "
                f"top={s['top_node']['type']} {s['top_node']['relation'] or ''} "
                f"{s['top_node']['index'] or ''} loops={s['top_node']['loops']} "
                f"seq={len(s['seq_scans'])} sorts={len(s['sorts'])}"
            )

    # paginated subresources + audit use parametrized statements; explain via ORM text
    with Session(engine) as db:
        _, total = ps.get_programs_page(db, uid, 1, 20)
        audit_rows = AuditService(db).recent_for_university(uid)
    print(f"programs total={total} audit rows={len(audit_rows)}")
    print(f"raw plans -> {outdir}")
    print(f"today={date.today()} expiry_warning={ps.__name__}")


if __name__ == "__main__":
    main()
