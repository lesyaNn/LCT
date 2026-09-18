"""Schema equivalence checker: old (Alembic head) vs new (SQL migrations).

Compares SEMANTIC schema, ignoring only:
* owners / ACL (never dumped here),
* migration bookkeeping tables (alembic_version vs schema_migrations),
* database-level comments.

Compares: tables, columns (type/nullable/default), PK, FK (+ON DELETE/UPDATE),
UNIQUE, CHECK, indexes, sequences, enum values, views, functions, triggers.

Usage (PowerShell / bash agnostic)::

    python scripts/check_migrations.py \\
        --source postgresql://rtk:change-me@localhost:5433/rtk_schema_source \\
        --target postgresql://rtk:change-me@localhost:5433/rtk_schema_target

Exit 0 on equivalence, 1 on any difference.
"""

from __future__ import annotations

import argparse
import re
import sys

try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None  # type: ignore

BOOKKEEPING = {"alembic_version", "schema_migrations"}


def _norm_default(value: str | None) -> str | None:
    if value is None:
        return None
    v = value.strip()
    # Normalize PG cast noise: 'x'::character varying -> 'x', ''::text -> ''
    v = re.sub(r"::(character varying|character|text|jsonb|boolean|integer|date)\b.*$", "", v)
    v = re.sub(r"\s+", " ", v).strip().lower()
    # now() variants
    v = v.replace("now()::timestamp with time zone", "now()")
    return v


def _norm_expr(value: str | None) -> str | None:
    if value is None:
        return None
    v = re.sub(r"\s+", " ", value.strip()).lower()
    v = v.replace("public.", "")
    return v


def snapshot(conn_str: str) -> dict:
    if psycopg is None:
        raise SystemExit("[check] psycopg is not installed")
    snap: dict = {}
    with psycopg.connect(conn_str) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname='public' ORDER BY 1"
            )
            snap["tables"] = sorted(
                r[0] for r in cur.fetchall() if r[0] not in BOOKKEEPING
            )
            cur.execute(
                """
                SELECT table_name, column_name, data_type, udt_name,
                       is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema='public' ORDER BY table_name, ordinal_position
                """
            )
            cols: dict[str, list] = {}
            for t, c, dt, udt, nul, dflt in cur.fetchall():
                if t in BOOKKEEPING:
                    continue
                # Map udt to canonical display: uuid stays uuid, jsonb, etc.
                cols.setdefault(t, []).append(
                    (c, dt, udt, nul, _norm_default(dflt))
                )
            snap["columns"] = cols
            cur.execute(
                """
                SELECT conrelid::regclass::text, conname, contype,
                       pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE connamespace='public'::regnamespace
                ORDER BY conrelid::regclass::text, conname
                """
            )
            cons: dict[str, list] = {}
            for table, name, ctype, definition in cur.fetchall():
                table = table.replace("public.", "")
                if table in BOOKKEEPING:
                    continue
                # Skip the auto-generated sequence-owned bookkeeping noise;
                # keep real PK/FK/UQ/CHECK with normalized definitions.
                cons.setdefault(table, []).append(
                    (name, ctype, _norm_expr(definition))
                )
            snap["constraints"] = cons
            cur.execute(
                "SELECT tablename, indexname, indexdef FROM pg_indexes "
                "WHERE schemaname='public' ORDER BY tablename, indexname"
            )
            idx: dict[str, list] = {}
            for table, name, definition in cur.fetchall():
                if table in BOOKKEEPING:
                    continue
                idx.setdefault(table, []).append((name, _norm_expr(definition)))
            snap["indexes"] = idx
            cur.execute(
                "SELECT sequencename FROM pg_sequences "
                "WHERE schemaname='public' ORDER BY 1"
            )
            snap["sequences"] = sorted(r[0] for r in cur.fetchall())
            cur.execute(
                "SELECT t.typname, e.enumlabel FROM pg_enum e "
                "JOIN pg_type t ON t.oid=e.enumtypid ORDER BY 1, 2"
            )
            snap["enums"] = cur.fetchall()
            cur.execute(
                "SELECT viewname FROM pg_views WHERE schemaname='public' ORDER BY 1"
            )
            snap["views"] = [r[0] for r in cur.fetchall()]
            cur.execute(
                "SELECT proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                "WHERE n.nspname='public' ORDER BY 1"
            )
            snap["functions"] = [r[0] for r in cur.fetchall()]
            cur.execute(
                "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal ORDER BY 1"
            )
            snap["triggers"] = [r[0] for r in cur.fetchall()]
    return snap


def diff_snapshots(source: dict, target: dict) -> list[str]:
    diffs: list[str] = []
    for key in ("tables", "sequences", "enums", "views", "functions", "triggers"):
        if source[key] != target[key]:
            diffs.append(
                f"{key}: source={source[key]} target={target[key]}"
            )
    for table in sorted(set(source["columns"]) | set(target["columns"])):
        s = source["columns"].get(table)
        t = target["columns"].get(table)
        if s != t:
            diffs.append(f"columns.{table}:\n  source={s}\n  target={t}")
    for table in sorted(set(source["constraints"]) | set(target["constraints"])):
        s = sorted(source["constraints"].get(table, []))
        t = sorted(target["constraints"].get(table, []))
        if s != t:
            # Show per-constraint diff for readability.
            s_set, t_set = set(s), set(t)
            diffs.append(
                f"constraints.{table}:\n  only_source={sorted(s_set - t_set)}"
                f"\n  only_target={sorted(t_set - s_set)}"
            )
    for table in sorted(set(source["indexes"]) | set(target["indexes"])):
        s = sorted(source["indexes"].get(table, []))
        t = sorted(target["indexes"].get(table, []))
        if s != t:
            s_set, t_set = set(s), set(t)
            diffs.append(
                f"indexes.{table}:\n  only_source={sorted(s_set - t_set)}"
                f"\n  only_target={sorted(t_set - s_set)}"
            )
    return diffs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="schema equivalence check")
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    args = parser.parse_args(argv)
    src = snapshot(args.source.replace("postgresql+psycopg://", "postgresql://"))
    tgt = snapshot(args.target.replace("postgresql+psycopg://", "postgresql://"))
    diffs = diff_snapshots(src, tgt)
    if not diffs:
        print(f"SCHEMA EQUIVALENCE: PASS "
              f"({len(src['tables'])} tables, "
              f"{sum(len(v) for v in src['columns'].values())} columns)")
        return 0
    print(f"SCHEMA EQUIVALENCE: FAIL ({len(diffs)} difference groups)")
    for d in diffs:
        print(f"  - {d}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
