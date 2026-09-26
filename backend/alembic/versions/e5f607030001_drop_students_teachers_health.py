"""Drop students/teachers/health-score entities (parity for SQL 000029).

Revision ID: e5f607030001. Depends on d4e707020001.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f607030001"
down_revision: str | Sequence[str] | None = "d4e707020001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("external_applications") as batch:
        batch.drop_column("student_id")
    for table in (
        "health_score_current",
        "health_score_snapshots",
        "teacher_programs",
        "teacher_certificates",
        "teacher_qualifications",
        "teachers",
        "students",
    ):
        op.drop_table(table)


def downgrade() -> None:
    pass
