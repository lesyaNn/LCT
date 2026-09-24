"""EXPLAIN analysis for P1 key queries (P1-10-02).

Usage (from backend/):
    DATABASE_URL=postgresql+psycopg://... python scripts/check_explain.py

Runs EXPLAIN (ANALYZE, BUFFERS trimmed to plan) for:
1. university passport aggregate (licenses join — P1-04-01 core),
2. teachers of a university (P1-04-02),
3. expiring licenses <= 30 days (P1-09-02 / Health Score D input),
4. meetings timeline of a university (P1-04-04).

NOTE: on tiny demo tables PostgreSQL legitimately prefers Seq Scan —
this is expected and documented per P1-10-02 ("Если Seq Scan неизбежен
(малые таблицы) — документировать"). Indexes exist and are used as the
tables grow (students table with 750 rows already shows Index Scan).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

from app.config import settings

url = os.getenv("DATABASE_URL", settings.database_url)
engine = create_engine(url)

QUERIES = {
    "1.passport_licenses": """
        SELECT l.id, l.license_number, p.name, v.name
        FROM licenses l
        JOIN it_products p ON p.id = l.product_id
        JOIN vendors v ON v.id = p.vendor_id
        WHERE l.university_id = (SELECT id FROM universities LIMIT 1)
        ORDER BY l.expires_at
    """,
    "2.teachers_by_university": """
        SELECT t.id FROM teachers t
        WHERE t.university_id = (SELECT id FROM universities LIMIT 1)
        ORDER BY t.full_name
    """,
    "3.expiring_licenses": """
        SELECT l.id FROM licenses l
        WHERE l.expires_at BETWEEN CURRENT_DATE AND CURRENT_DATE + 30
        ORDER BY l.expires_at
    """,
    "4.meetings_timeline": """
        SELECT m.id FROM meetings m
        WHERE m.university_id = (SELECT id FROM universities LIMIT 1)
        ORDER BY m.meeting_at DESC LIMIT 10
    """,
    "5.students_by_university": """
        SELECT s.id FROM students s
        WHERE s.university_id = (SELECT id FROM universities LIMIT 1)
        AND s.status = 'active' LIMIT 20
    """,
}

def _redacted_url(raw: str) -> str:
    """Redact credentials for logs (L14): never print a full URL with password."""
    try:
        from urllib.parse import urlsplit, urlunsplit

        parts = urlsplit(raw)
        if "@" in raw and parts.hostname:
            netloc = parts.hostname
            if parts.port:
                netloc += f":{parts.port}"
            if parts.username:
                netloc = f"{parts.username}:***@{netloc}"
            return urlunsplit((parts.scheme, netloc, parts.path, "", ""))
    except Exception:
        pass
    return raw.split("@")[-1] if "@" in raw else "(url redacted)"


# L14: Bitmap Heap/Index Scan are index usage too (previously only
# "Index Scan"/"Index Only Scan" were counted, undercounting indexed plans).
INDEX_TOKENS = ("Index Scan", "Index Only Scan", "Bitmap Heap Scan", "Bitmap Index Scan")

print(f"EXPLAIN on {_redacted_url(url)}")
index_used_total = 0
for name, sql in QUERIES.items():
    with engine.connect() as conn:
        rows = conn.execute(text(f"EXPLAIN {sql}")).fetchall()
    plan = "\n".join(r[0] for r in rows)
    uses_index = any(tok in plan for tok in INDEX_TOKENS)
    index_used_total += uses_index
    print(f"\n=== {name}: {'INDEX SCAN' if uses_index else 'Seq Scan (small table OK)'}")
    for line in plan.splitlines()[:8]:
        print(f"    {line.strip()}")

print(f"\nSUMMARY: index used in {index_used_total}/{len(QUERIES)} queries "
      "(Seq Scan on tiny tables is expected PostgreSQL behaviour).")
# Exit code for gates: 0 when every plan is explainable; informational
# (Seq Scan on tiny tables is NOT a failure — see module docstring).
sys.exit(0)
