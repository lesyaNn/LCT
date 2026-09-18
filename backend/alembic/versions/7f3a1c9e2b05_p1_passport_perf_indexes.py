"""P1-04-06: composite passport indexes for ORDER BY + LIMIT per university.

The passport interaction block filters by ``university_id`` and sorts by a
timestamp with a small LIMIT
(documents ``ORDER BY created_at DESC LIMIT 20``,
notes ``ORDER BY created_at DESC LIMIT 10``). Single-column indexes on
``university_id`` exist, but without the composite the DB must sort the
university's rows on every request. Meetings already had the analogous
composite (``ix_meetings_univ_meeting_at``) and audit has
``ix_audit_events_univ_created`` — these two close the same gap for the
remaining passport-ordered collections. No duplication, no EXPLAIN-level
analysis here (that is P1-10-02); this only removes the obviously
missing per-university ordering support.

Revision ID: 7f3a1c9e2b05. Depends on 7f3a1c9e2b04.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "7f3a1c9e2b05"
down_revision: str | Sequence[str] | None = "7f3a1c9e2b04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_documents_univ_created",
        "documents",
        ["university_id", "created_at"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_interaction_notes_univ_created",
        "interaction_notes",
        ["university_id", "created_at"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_interaction_notes_univ_created", table_name="interaction_notes")
    op.drop_index("ix_documents_univ_created", table_name="documents")
