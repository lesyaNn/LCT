"""P1-10-02: composite readiness indexes for the passport teachers query.

BEFORE (performance dataset, 60 univs / 534 teachers / 1550 links,
``EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`` on the REAL passport
teachers statement — 10 teachers x 3 programs = 30 outer rows):

* six correlated readiness scalars did ``Bitmap Heap Scan`` /
  ``Index Scan`` on the single-column ``..._teacher_id`` indexes with
  ``Filter: expires_at ...`` + heap fetch per loop (``loops=30``);
* passport_4_teachers: Execution ~2.0-2.6 ms, Shared Hit 565,
  planner Total Cost ~1941.

AFTER (same dataset, same statement, ``ANALYZE`` after the build):

* scalars use ``Index Scan`` / ``Index Only Scan`` on the new
  composites with ``Index Cond: teacher_id = ... AND expires_at ...``;
* passport_4_teachers: Execution ~1.7 ms, Shared Hit 442 (-22%),
  planner Total Cost ~1160 (-40%).

Why these two and nothing else (all verified with BEFORE/AFTER
EXPLAIN on the same dataset):

* ``students (university_id, program_id, status)`` was tested and
  REJECTED — the planner only constrains the leading column and the
  numbers did not move (exec 0.34 -> 0.37 ms, buffers unchanged).
* ``licenses`` already has ``(university_id, expires_at)``;
  ``contracts`` per-university branches are 230-row Seq Scans at
  ~0.02 ms — no measured problem, no index.
* ``ix_audit_events_university_id`` is a near-duplicate prefix of
  ``ix_audit_events_univ_created`` but is kept (cheap, serves
  hypothetical filter-only lookups; removal would need its own proof).

Revision ID: 7f3a1c9e2b06. Depends on 7f3a1c9e2b05.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "7f3a1c9e2b06"
down_revision: str | Sequence[str] | None = "7f3a1c9e2b05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_teacher_certificates_teacher_expires",
        "teacher_certificates",
        ["teacher_id", "expires_at"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_teacher_qualifications_teacher_expires",
        "teacher_qualifications",
        ["teacher_id", "expires_at"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_teacher_qualifications_teacher_expires",
        table_name="teacher_qualifications",
    )
    op.drop_index(
        "ix_teacher_certificates_teacher_expires",
        table_name="teacher_certificates",
    )
