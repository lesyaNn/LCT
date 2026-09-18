"""PostgreSQL schema inspection.

Usage (from backend/):
    DATABASE_URL=postgresql+psycopg://postgres@localhost:55433/rtk_p1 \
        python scripts/db_inspect.py

Prints: tables, key FKs, indexes, SQL migration version.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect, text

from app.config import settings

url = os.getenv("DATABASE_URL", settings.database_url)
engine = create_engine(url)
insp = inspect(engine)

tables = sorted(insp.get_table_names())
print(f"TABLES ({len(tables)}):")
for t in tables:
    print(f"  - {t}")

print("\nFOREIGN KEYS:")
for t in tables:
    for fk in insp.get_foreign_keys(t):
        print(
            f"  - {t}.{fk['constrained_columns']} -> "
            f"{fk['referred_table']}.{fk['referred_columns']} "
            f"(name={fk['name']}, ondelete={fk['options'].get('ondelete')})"
        )

print("\nINDEXES:")
for t in tables:
    for ix in insp.get_indexes(t):
        print(f"  - {t}.{ix['name']}: {ix['column_names']} (unique={ix['unique']})")

print("\nTIMESTAMPTZ check (created_at/updated_at):")
with engine.connect() as conn:
    rows = conn.execute(
        text(
            "SELECT table_name, column_name, data_type "
            "FROM information_schema.columns "
            "WHERE column_name IN ('created_at','updated_at') "
            "AND table_schema='public' ORDER BY 1,2"
        )
    ).fetchall()
    bad = [r for r in rows if r[2] != "timestamp with time zone"]
    for r in rows:
        print(f"  - {r[0]}.{r[1]}: {r[2]}")
    print(f"  => {'ALL TIMESTAMPTZ' if not bad else 'MISMATCH: ' + str(bad)}")

print("\nMIGRATION VERSION (schema_migrations; alembic_version = legacy only):")
with engine.connect() as conn:
    try:
        rows = conn.execute(text("SELECT version FROM schema_migrations ORDER BY 1")).fetchall()
        for r in rows:
            print(f"  - {r[0]}")
        if not rows:
            print("  - (no applied SQL migrations)")
    except Exception as exc:  # noqa: BLE001
        print(f"  - (no schema_migrations table: {exc})")
    try:
        rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
        for r in rows:
            print(f"  - legacy alembic: {r[0]}")
    except Exception:  # noqa: BLE001
        print("  - (no legacy alembic_version table)")
