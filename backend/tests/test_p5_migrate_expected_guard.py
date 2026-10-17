"""L8: EXPECTED_TABLES stays in sync with migrations (pure-unit, no database).

Parses ``CREATE TABLE`` statements from ``migrations/*.up.sql`` and pins:
* every created table is listed in ``migrate.EXPECTED_TABLES``;
* every ``EXPECTED_TABLES`` entry is created by some migration
  (catches both missing additions and stale removals that would cause
  false DRIFT under ``set -e`` in ``entrypoint.sh``).
"""

import importlib.util
import os
import re

import pytest

CREATE_RE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)", re.IGNORECASE)
DROP_RE = re.compile(r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(\w+)", re.IGNORECASE)


def _load_migrate():
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "migrate.py"
    )
    spec = importlib.util.spec_from_file_location("sql_migrate_guard", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _created_tables():
    migrations = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations"
    )
    found: set[str] = set()
    for name in sorted(os.listdir(migrations)):
        if not name.endswith(".up.sql"):
            continue
        text = open(os.path.join(migrations, name), encoding="utf-8").read()
        # Apply operations in order: 000036 recreates tables dropped in 000029.
        operations = [(match.start(), True, match.group(1)) for match in CREATE_RE.finditer(text)]
        operations += [(match.start(), False, match.group(1)) for match in DROP_RE.finditer(text)]
        for _, created, table in sorted(operations):
            if created:
                found.add(table)
            else:
                found.discard(table)
    return found - {"schema_migrations"}


def test_expected_tables_matches_migrations():
    module = _load_migrate()
    created = _created_tables()
    expected = set(module.EXPECTED_TABLES)
    assert created - expected == set(), f"tables missing from EXPECTED_TABLES: {created - expected}"
    assert expected - created == set(), f"stale EXPECTED_TABLES entries: {expected - created}"


def test_no_duplicate_expected_tables():
    module = _load_migrate()
    assert len(module.EXPECTED_TABLES) == len(set(module.EXPECTED_TABLES))


def test_migration_numbers_are_unique():
    versions = [version for version, _, _ in _load_migrate()._discover()]
    numbers = [version.split("_", 1)[0] for version in versions]
    assert len(numbers) == len(set(numbers)), "duplicate migration number"


def test_migrator_rejects_duplicate_number_before_sql(tmp_path, monkeypatch):
    for name in ("000001_first", "000001_second"):
        (tmp_path / f"{name}.up.sql").write_text("SELECT 1", encoding="utf-8")
        (tmp_path / f"{name}.down.sql").write_text("SELECT 1", encoding="utf-8")
    module = _load_migrate()
    monkeypatch.setattr(module, "MIGRATIONS_DIR", tmp_path)
    with pytest.raises(SystemExit, match="duplicate migration number 000001"):
        module._discover()
