"""P2-09-01: health_score_snapshots (Alembic parity for SQL 000011).

Active schema path is ``migrations/000011_health_snapshots.{up,down}.sql``
(``scripts/migrate.py``); this revision mirrors the same DDL/names so
``scripts/check_migrations.py`` stays green. New databases use the SQL
runner; Alembic is kept for the legacy adoption path only.

Revision ID: b2c909010901. Depends on 7f3a1c9e2b06 (old head).
Endpoint GET .../health-score/history и cron/event писатели — позже.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2c909010901"
down_revision: str | Sequence[str] | None = "7f3a1c9e2b06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "health_score_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("university_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "breakdown",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_day", sa.Date(), nullable=False),
        sa.Column(
            "trigger_event",
            sa.String(64),
            nullable=False,
            server_default="daily_cron",
        ),
        sa.ForeignKeyConstraint(
            ["university_id"],
            ["universities.id"],
            name="fk_health_snapshots_university_id_universities",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_health_score_snapshots"),
        sa.UniqueConstraint(
            "university_id",
            "period_day",
            "trigger_event",
            name="uq_health_snapshots_uni_day_trigger",
        ),
    )
    op.create_index(
        "ix_health_snapshots_university_id",
        "health_score_snapshots",
        ["university_id"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_health_snapshots_univ_calculated",
        "health_score_snapshots",
        ["university_id", sa.text("calculated_at DESC")],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_health_snapshots_univ_calculated",
        table_name="health_score_snapshots",
    )
    op.drop_index(
        "ix_health_snapshots_university_id",
        table_name="health_score_snapshots",
    )
    op.drop_table("health_score_snapshots")
