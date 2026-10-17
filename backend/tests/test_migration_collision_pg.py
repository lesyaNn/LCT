"""PostgreSQL regression for the one released Health Score migration rename."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from tests.db_helpers import _load_migrate_module, reset_test_db


def test_legacy_health_score_ledger_upgrade_and_down(monkeypatch):
    url = os.getenv("TEST_DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("requires dedicated PostgreSQL TEST_DATABASE_URL")

    engine = create_engine(url)
    try:
        reset_test_db(engine, url)
        observation_id, university_id = str(uuid4()), str(uuid4())
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO universities (id, name) VALUES (:id, 'migration legacy test')"),
                {"id": university_id},
            )
            conn.execute(
                text(
                    "INSERT INTO health_score_observations "
                    "(id, university_id, score, level, calculated_at) "
                    "VALUES (:id, :university_id, 78, 'good', now())"
                ),
                {"id": observation_id, "university_id": university_id},
            )
            conn.execute(
                text(
                    "UPDATE schema_migrations SET version = "
                    "'000043_health_score_observations' "
                    "WHERE version = '000047_health_score_observations'"
                )
            )

        migrate = _load_migrate_module()
        monkeypatch.setenv("DATABASE_URL", url)
        assert migrate.cmd_up() == 0
        assert migrate.cmd_verify() == 0
        with engine.connect() as conn:
            assert conn.scalar(
                text("SELECT score FROM health_score_observations WHERE id = :id"),
                {"id": observation_id},
            ) == 78
            versions = conn.execute(
                text(
                    "SELECT version FROM schema_migrations "
                    "WHERE substring(version from 1 for 6) BETWEEN '000043' AND '000047' "
                    "ORDER BY version"
                )
            ).scalars().all()
            assert versions == [
                "000043_notifications",
                "000044_assistant_conversations",
                "000045_meeting_agenda",
                "000046_workflow_meeting_drafts",
                "000047_health_score_observations",
            ]

        assert migrate.cmd_down("000046_workflow_meeting_drafts", confirm=True) == 0
        with engine.connect() as conn:
            for table in (
                "notifications",
                "assistant_conversations",
                "assistant_turns",
                "workflow_comments",
                "meetings",
            ):
                assert conn.scalar(text("SELECT to_regclass(:name)"), {"name": table})
            assert conn.scalar(text("SELECT to_regclass('health_score_observations')")) is None
    finally:
        engine.dispose()
