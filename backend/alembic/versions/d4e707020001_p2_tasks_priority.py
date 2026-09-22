"""P2-07-02: tasks.priority (Alembic parity for SQL 000013).

Active schema path is ``migrations/000013_tasks_priority.{up,down}.sql``
(``scripts/migrate.py``); this revision mirrors the same DDL/names so
``scripts/check_migrations.py`` stays green.

Revision ID: d4e707020001. Depends on b2c909010901.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e707020001"
down_revision: str | Sequence[str] | None = "b2c909010901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "priority",
            sa.String(32),
            nullable=False,
            server_default="normal",
        ),
    )
    op.create_index(
        "ix_tasks_instance_priority",
        "tasks",
        ["instance_id", "priority"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_instance_priority", table_name="tasks")
    op.drop_column("tasks", "priority")
