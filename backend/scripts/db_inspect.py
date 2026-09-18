"""PostgreSQL schema inspection (P1 task §20).

Usage (from backend/):
    DATABASE_URL=postgresql+psycopg://postgres@localhost:55433/rtk_p1 \
        python scripts/db_inspect.py

Prints: tables, key FKs, indexes, alembic version.
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

print("\nALEMBIC VERSION:")
with engine.connect() as conn:
    try:
        rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
        for r in rows:
            print(f"  - {r[0]}")
    except Exception as exc:  # noqa: BLE001
        print(f"  - (no version table: {exc})")
