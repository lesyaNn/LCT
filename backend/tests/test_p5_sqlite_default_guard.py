"""M10: SQLite default is test-only — PG is the sole prod schema source.

Pins (pure-unit, no database):
* the settings default stays SQLite (local/test convenience), i.e. nobody
  silently repoints the default at a production-looking PG URL;
* the SQL migration runner REFUSES SQLite (PG-native DDL only);
* the container entrypoint is fail-closed without ``DATABASE_URL``;
* ``/ready`` semantics are documented in ``docs/SQLITE_DEFAULT.md``.

The loud-warning/degraded-/ready behaviour itself lives in ``app/`` and is
owned by Dev-2 (out of the Dev-3 zone); this test locks the contract from
the outside so the default can never drift into prod unnoticed.
"""

import os

import pytest


def test_settings_default_is_sqlite_test_only():
    from app.config import settings

    assert settings.database_url.startswith("sqlite"), settings.database_url


def test_migrate_runner_refuses_sqlite(monkeypatch, tmp_path):
    import importlib.util

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/guard.db")
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "migrate.py"
    )
    spec = importlib.util.spec_from_file_location("sql_migrate_sqlite_guard", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(SystemExit):
        module._database_url()


def test_entrypoint_fail_closed_without_database_url():
    entrypoint = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "entrypoint.sh"
    )
    text = open(entrypoint, encoding="utf-8").read()
    assert "set -e" in text
    assert "DATABASE_URL is not set" in text
    assert "refusing to start without migrations" in text


def test_sqlite_default_contract_documented():
    doc = os.path.join(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ),
        "docs",
        "SQLITE_DEFAULT.md",
    )
    assert os.path.exists(doc), "docs/SQLITE_DEFAULT.md must exist (M10)"
    text = open(doc, encoding="utf-8").read()
    assert "/ready" in text and "sqlite" in text.lower()
